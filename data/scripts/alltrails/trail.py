import json
import os
import re
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from paths import DATASETS_DIR
from session import make_session


def find_api_key(html):
    key_match = re.search(r"key%3D([A-Za-z0-9]+)%26", html) or re.search(r"[?&]key=([A-Za-z0-9]+)&", html)
    if not key_match:
        raise RuntimeError("Could not auto-discover the AllTrails API key from the trail page HTML - the page structure may have changed.")

    api_key = key_match.group(1)

    print(f"discovered API key: {api_key}")

    return api_key


def find_features(html):
    return re.findall(r'<div class="PlanYourVisit_tagName__\w+">([^<]+)</div>', html)


def populate_trail_data(session, trail_id, headers, api_key, html):
    ld_json_blocks = re.findall(r'<script type="application/ld\+json">(.*?)</script>', html)
    trail_metadata = next(
        (json.loads(block) for block in ld_json_blocks if '"@type":"LocalBusiness"' in block),
        None,
    )
    if trail_metadata is None:
        raise RuntimeError("Could not find the trail's LocalBusiness JSON-LD block on the page.")

    trail_metadata["trailId"] = trail_id
    trail_metadata["features"] = find_features(html)
    trail_metadata["surfaceTypes"] = fetch_surface_types(session, trail_id, headers, api_key)

    trail_path = os.path.join(DATASETS_DIR, "raw_descriptions", f"{trail_id}.json")
    with open(trail_path, "w", encoding="utf-8") as f:
        json.dump(trail_metadata, f, indent=2, ensure_ascii=False)
    print(f"saved trail info to {trail_path}")

    return trail_metadata


def fetch_surface_types(session, trail_id, headers, api_key):
    url = f"https://www.alltrails.com/api/alltrails/trails/{trail_id}/surface_types?key={api_key}"
    resp = session.get(url, headers=headers)
    resp.raise_for_status()
    return resp.json()["surfaceTypes"]["aggregation"]


def fetch_trail_page(trail_url, headers):
    session = make_session()

    resp = session.get(trail_url, headers=headers)
    resp.raise_for_status()

    return session, resp.text


def scrape_page(trail_id, trail_url, headers):
    session, html = fetch_trail_page(trail_url, headers)

    html_path = os.path.join(DATASETS_DIR, "html", f"{trail_id}.html")
    with open(html_path, "w", encoding="utf-8") as f:
        f.write(html)
    print(f"saved trail page html to {html_path}")

    return session, html
