import time

PER_PAGE = 500


def fetch_reviews(session, headers, trail_id, api_key, per_page=PER_PAGE):
    """Fetch every review for a trail, paginating until AllTrails returns a
    short page. `session` must already carry a primed DataDome cookie (from
    having fetched a trail page first) and the AllTrails auth cookie.
    """
    all_reviews = []
    page = 1
    while True:
        url = (
            f"https://www.alltrails.com/api/alltrails/v2/trails/{trail_id}/reviews"
            f"?per_page={per_page}&page={page}&key={api_key}"
        )

        for attempt in range(4):
            try:
                resp = session.get(url, headers=headers, timeout=60)
                resp.raise_for_status()
                data = resp.json()
                break
            except Exception as exc:
                wait = 5 * (attempt + 1)
                print(f"page {page} attempt {attempt + 1} failed ({exc}); retrying in {wait}s")
                time.sleep(wait)
        else:
            raise RuntimeError(f"page {page} failed after all retries")

        batch = data.get("trail_reviews", [])
        all_reviews.extend(batch)
        print(f"page {page}: {len(batch)} reviews (total so far: {len(all_reviews)})")
        if len(batch) < per_page:
            break
        page += 1
        time.sleep(2)

    return all_reviews


if __name__ == "__main__":
    # Standalone mode: sets up its own session/cookie/API key so this file
    # can still be run and tested on its own, without going through
    # trail_page.py first.
    import json
    import os
    import re

    from curl_cffi import requests
    from dotenv import load_dotenv

    SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
    DATA_DIR = os.path.dirname(SCRIPT_DIR)
    load_dotenv(os.path.join(DATA_DIR, ".env"))

    TRAIL_URL = "https://www.alltrails.com/trail/canada/ontario/the-crack-trail"
    TRAIL_ID = 10239525

    headers = {
        "User-Agent": (
            "Mozilla/5.0 (iPhone; CPU iPhone OS 17_0 like Mac OS X) "
            "AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.0 Mobile/15E148 Safari/604.1"
        ),
        "Accept": "application/json",
        "Referer": TRAIL_URL,
    }

    session = requests.Session(impersonate="safari_ios")
    session.cookies.set("_alltrails_session", os.environ["ALLTRAILS_SESSION_COOKIE"], domain=".alltrails.com")

    page_resp = session.get(TRAIL_URL, headers=headers)
    key_match = re.search(r"key%3D([A-Za-z0-9]+)%26", page_resp.text) or re.search(
        r"[?&]key=([A-Za-z0-9]+)&", page_resp.text
    )
    if not key_match:
        raise RuntimeError("Could not auto-discover the AllTrails API key from the trail page HTML.")
    api_key = key_match.group(1)

    reviews = fetch_reviews(session, headers, TRAIL_ID, api_key)

    out_path = os.path.join(DATA_DIR, "raw_reviews", "the_crack_trail_reviews.json")
    with open(out_path, "w", encoding="utf-8") as f:
        json.dump(reviews, f, indent=2, ensure_ascii=False)

    print(f"\nTotal reviews collected: {len(reviews)}")
    print(f"saved to {out_path}")
