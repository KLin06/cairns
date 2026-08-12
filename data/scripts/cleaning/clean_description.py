import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from paths import DATASETS_DIR

_explore_index = None

def _load_explore_index():
    # Read explore/top_100_ontario_trails.json once and cache it, keyed by
    # trail id, so a loop calling clean_description() per trail doesn't
    # re-read and re-parse the same ~100-record file on every call.
    global _explore_index
    if _explore_index is None:
        path = os.path.join(DATASETS_DIR, "explore", "top_100_ontario_trails.json")
        with open(path, "r", encoding="utf-8") as f:
            records = json.load(f)
        _explore_index = {str(r["ID"]): r for r in records}
    return _explore_index


def clean_description(trail_id):
    path = os.path.join(DATASETS_DIR, "raw_descriptions", f"{trail_id}.json")

    with open(path, "r", encoding="utf-8") as f:
        trail_info = json.load(f)

    explore_index = _load_explore_index()
    explore_record = explore_index.get(str(trail_id))
    if explore_record is None:
        raise KeyError(f"trail {trail_id} not found in the explore index - re-run explore.py or check the id")

    address = trail_info["address"]
    geo = trail_info["geo"]
    rating = trail_info["aggregateRating"]

    cleaned = {
        "trailId": trail_info["trailId"],
        "name": trail_info["name"],
        "description": trail_info["description"],
        "addressLocality": address["addressLocality"],
        "latitude": float(geo["latitude"]),
        "longitude": float(geo["longitude"]),
        "ratingValue": rating["ratingValue"],
        "reviewCount": rating["reviewCount"],
        "worstRating": rating["worstRating"],
        "bestRating": rating["bestRating"],
        "images": trail_info["image"],
        "features": trail_info["features"],
        "surfaceTypes": [
            {
                "label": s["surfaceType"]["label"].lower(),
                "percentOfSurface": s["percentOfSurface"],
                "totalLength": s["totalLength"],
            }
            for s in trail_info["surfaceTypes"]
        ],
        "length": explore_record["length"],
        "durationMinutes": explore_record["duration_minutes"],
        "difficultyRating": explore_record["difficulty_rating"],
        "areaName": explore_record["area_name"],
        "popularity": explore_record["popularity"],
    }

    new_path = os.path.join(DATASETS_DIR, "cleaned_descriptions", f"{trail_id}.json")

    with open(new_path, "w", encoding="utf-8") as f:
        json.dump(cleaned, f, indent=2, ensure_ascii=False)

    print(f"saved cleaned trail info to {new_path}")
