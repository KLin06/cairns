import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from paths import DATASETS_DIR
from session import build_headers
from trail import fetch_trail_page, find_api_key

EXPLORE_URL = "https://www.alltrails.com/api/alltrails/explore/v1/search?nls=false"

RECORD_ATTRIBUTES = [
    "ID", "location_label", "location_type", "name", "photos_count", "slug", "subtype",
    "popularity", "state_name", "trails_count", "type_label", "_geoloc", "area_name",
    "avg_rating", "area_slug", "city_url", "difficulty_rating", "description",
    "duration_minutes", "duration_minutes_cycling", "duration_minutes_hiking",
    "duration_minutes_mountain_biking", "duration_minutes_trail_running",
    "estimated_time_to_complete", "has_profile_photo", "is_closed", "length",
    "num_reviews", "num_photos", "profile_photo_url", "_cluster_geoloc", "type", "area_type",
]


def fetch_explore_trails(session, trail_url, api_key, top_left, bottom_right, activity="hiking", length_min=None, length_max=None):
    # Search the /explore map's trail index for a bounding box. This is the
    # same endpoint the interactive map fires on pan/zoom - not documented,
    # found by inspecting the request in DevTools.

    filters = {"hasTrails": True}
    if activity:
        filters["activity"] = [activity]
    if length_min is not None or length_max is not None:
        filters["length"] = {"min": length_min, "max": length_max}

    body = {
        "filters": filters,
        "recordTypesToReturn": ["trail"],
        "location": {
            "mapRotation": 0,
            "topLeft": top_left,
            "topRight": {"lat": top_left["lat"], "lng": bottom_right["lng"]},
            "bottomLeft": {"lat": bottom_right["lat"], "lng": top_left["lng"]},
            "bottomRight": bottom_right,
        },
        "recordAttributesToRetrieve": RECORD_ATTRIBUTES,
        "resultsToInclude": ["searchResults", "summary"],
    }

    headers = {
        **build_headers(trail_url),
        "Accept": "*/*",
        "Content-Type": "application/json",
        "Origin": "https://www.alltrails.com",
        "x-at-caller": "Mugen",
        "x-at-key": api_key,
    }

    resp = session.post(EXPLORE_URL, headers=headers, json=body)
    resp.raise_for_status()
    data = resp.json()
    return data["searchResults"], data["summary"]


if __name__ == "__main__":
    top_left = {"lat": 49.9495463726704, "lng": -96.7447701014953}
    bottom_right = {"lat": 41.413953215399545, "lng": -73.27593989850502}
    trail_url = "https://www.alltrails.com/trail/canada/ontario/the-crack-trail"
    headers = build_headers(trail_url)

    session, html = fetch_trail_page(trail_url, headers)
    api_key = find_api_key(html)

    results, summary = fetch_explore_trails(
        session, trail_url, api_key, top_left, bottom_right,
        activity="hiking", length_min=5000, length_max=56000,
    )
    print(f"{summary['displayText']} matched; {len(results)} trail records returned")

    ontario_trails = [
        r for r in results
        if r.get("slug", "").startswith("trail/canada/ontario/") and r.get("is_closed") is False
    ]
    ontario_trails.sort(key=lambda r: r["popularity"], reverse=True)
    print(f"{len(ontario_trails)} of those are in Ontario and open")

    top_100 = ontario_trails[:100]

    out_path = os.path.join(DATASETS_DIR, "explore", "top_100_ontario_trails.json")
    os.makedirs(os.path.dirname(out_path), exist_ok=True)
    with open(out_path, "w", encoding="utf-8") as f:
        json.dump(top_100, f, indent=2, ensure_ascii=False)

    print(f"saved top {len(top_100)} Ontario trails to {out_path}")
