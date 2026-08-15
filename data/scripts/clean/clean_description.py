import json
import os

from scripts.paths import DATASETS_DIR

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

    # Not every trail's raw_descriptions/explore-index record has every
    # field (some trails are missing e.g. duration_minutes or area_name
    # entirely, not just null) - only lat/lng stay required below, since
    # weather/terrain enrichment can't do anything without coordinates;
    # everything else degrades to None rather than failing the whole trail.
    address = trail_info.get("address") or {}
    geo = trail_info["geo"]
    rating = trail_info.get("aggregateRating") or {}

    cleaned = {
        "trailId": trail_info["trailId"],
        "trailSlug": explore_record.get("slug"),
        "name": trail_info.get("name"),
        "description": trail_info.get("description"),
        "addressLocality": address.get("addressLocality"),
        "latitude": float(geo["latitude"]),
        "longitude": float(geo["longitude"]),
        "ratingValue": rating.get("ratingValue"),
        "reviewCount": rating.get("reviewCount"),
        "worstRating": rating.get("worstRating"),
        "bestRating": rating.get("bestRating"),
        "images": trail_info.get("image"),
        "features": trail_info.get("features") or [],
        "surfaceTypes": [
            {
                "label": s["surfaceType"]["label"].lower(),
                "percentOfSurface": s.get("percentOfSurface"),
                "totalLength": s.get("totalLength"),
            }
            for s in (trail_info.get("surfaceTypes") or [])
        ],
        "length": explore_record.get("length"),
        "durationMinutes": explore_record.get("duration_minutes"),
        "difficultyRating": explore_record.get("difficulty_rating"),
        "areaName": explore_record.get("area_name"),
        "popularity": explore_record.get("popularity"),
    }

    new_path = os.path.join(DATASETS_DIR, "cleaned_descriptions", f"{trail_id}.json")

    with open(new_path, "w", encoding="utf-8") as f:
        json.dump(cleaned, f, indent=2, ensure_ascii=False)

    print(f"saved cleaned trail info to {new_path}")
