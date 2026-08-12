import json
import os
import re

from curl_cffi import requests
from dotenv import load_dotenv

from reviews import fetch_reviews

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
DATA_DIR = os.path.dirname(SCRIPT_DIR)
load_dotenv(os.path.join(DATA_DIR, ".env"))

TRAIL_URL = "https://www.alltrails.com/trail/canada/ontario/the-crack-trail"
TRAIL_ID = 10239525

SESSION_COOKIE = os.environ["ALLTRAILS_SESSION_COOKIE"]

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (iPhone; CPU iPhone OS 17_0 like Mac OS X) "
        "AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.0 Mobile/15E148 Safari/604.1"
    ),
    "Accept": "application/json",
    "Referer": TRAIL_URL,
}


def fetch_trail_page(trail_url):
    """Fetch the trail's main page: primes the DataDome cookie for this
    session, discovers the frontend's public API key, and pulls the
    trail's own metadata (name, description, geo, rating) out of its
    embedded schema.org JSON-LD block.

    Returns (session, api_key, trail_metadata). The returned session
    carries the DataDome cookie this fetch just earned, so it can be
    reused directly for the reviews API instead of re-priming it.
    """
    session = requests.Session(impersonate="safari_ios")
    session.cookies.set("_alltrails_session", SESSION_COOKIE, domain=".alltrails.com")

    resp = session.get(trail_url, headers=HEADERS)
    resp.raise_for_status()

    # The frontend's public API key isn't documented anywhere; it's embedded
    # in the page's static-map URLs, so we scrape it out instead of
    # hardcoding it - that's what lets this survive the key rotating,
    # instead of re-finding it by hand in DevTools each time.
    key_match = re.search(r"key%3D([A-Za-z0-9]+)%26", resp.text) or re.search(
        r"[?&]key=([A-Za-z0-9]+)&", resp.text
    )
    if not key_match:
        raise RuntimeError(
            "Could not auto-discover the AllTrails API key from the trail page HTML - "
            "the page structure may have changed."
        )
    api_key = key_match.group(1)

    # The trail's LocalBusiness JSON-LD block is a clean, purpose-built
    # source for name/description/geo/rating - unlike the reviews data,
    # this doesn't need regex-scraping out of a React streaming payload.
    # Note: it does NOT include the trail's "features" tags (Forests,
    # Rivers, Scramble, etc.) - those aren't present anywhere in this
    # page's HTML.
    ld_json_blocks = re.findall(r'<script type="application/ld\+json">(.*?)</script>', resp.text)
    trail_metadata = next(
        (json.loads(block) for block in ld_json_blocks if '"@type":"LocalBusiness"' in block),
        None,
    )
    if trail_metadata is None:
        raise RuntimeError("Could not find the trail's LocalBusiness JSON-LD block on the page.")

    return session, api_key, trail_metadata


if __name__ == "__main__":
    session, api_key, trail_metadata = fetch_trail_page(TRAIL_URL)
    print(f"discovered API key: {api_key}")
    print(f"trail: {trail_metadata['name']}")

    datasets_dir = os.path.join(DATA_DIR, "datasets")

    trail_path = os.path.join(datasets_dir, "raw_descriptions", "the_crack_trail_info.json")
    with open(trail_path, "w", encoding="utf-8") as f:
        json.dump(trail_metadata, f, indent=2, ensure_ascii=False)
    print(f"saved trail info to {trail_path}")

    reviews = fetch_reviews(session, HEADERS, TRAIL_ID, api_key)

    reviews_path = os.path.join(datasets_dir, "raw_reviews", "the_crack_trail_reviews.json")
    with open(reviews_path, "w", encoding="utf-8") as f:
        json.dump(reviews, f, indent=2, ensure_ascii=False)

    print(f"\nTotal reviews collected: {len(reviews)}")
    print(f"saved to {reviews_path}")
