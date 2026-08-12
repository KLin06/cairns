import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from paths import DATASETS_DIR

def clean_description(trail_id):
    path = os.path.join(DATASETS_DIR, "raw_descriptions", f"{trail_id}.json")

    with open(path, "r", encoding="utf-8") as f:
        trail_info = json.load(f)

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
    }

    new_path = os.path.join(DATASETS_DIR, "cleaned_descriptions", f"{trail_id}.json")

    with open(new_path, "w", encoding="utf-8") as f:
        json.dump(cleaned, f, indent=2, ensure_ascii=False)

    print(f"saved cleaned trail info to {new_path}")
