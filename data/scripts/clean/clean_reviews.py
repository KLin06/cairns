import json
import os
import sys

import pandas as pd

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from paths import DATASETS_DIR

def clean_reviews(trail_id):
    path = os.path.join(DATASETS_DIR, "raw_reviews", f"{trail_id}.json")

    df = pd.read_json(path)
    df = df.rename(columns={"id": "reviewId"})

    df = df[df["comment_lang"] == "en-US"]

    df["activity"] = df["activity"].apply(lambda a: a["name"] if isinstance(a, dict) else None)

    for col in ["ratingAttributes", "infoAttributes", "obstacles", "trailConditions", "commentFeatures"]:
        df[col] = df[col].apply(lambda items: [item["name"] for item in items] if isinstance(items, list) else [])

    df["hasRecording"] = df["associatedRecording"].apply(lambda r: isinstance(r, dict))

    df = df[df["activity"].isin(["Hiking", "Backpacking"])]

    df.drop(
        columns=[
            "comment_original",
            "replies",
            "associatedRecording",
            "user",
            "badges",
            "summaryExclusion",
            "commentActivities",
            "votes",
            "comment_html",
            "comment_original_html",
            "difficultyChipUids",
            "difficultyAttributes",
            "comment_source",
            "trailSlug",
            "trailLocation",
            "trailName",
            "comment_lang",
            "dataUid",
            "metadata",
        ],
        inplace=True,
    )

    new_path = os.path.join(DATASETS_DIR, "cleaned_reviews", f"{trail_id}.json")

    records = json.loads(df.to_json(orient="records", force_ascii=False, date_format="iso"))
    with open(new_path, "w", encoding="utf-8") as f:
        json.dump(records, f, indent=2, ensure_ascii=False)

    print(f"saved {len(df)} cleaned reviews to {new_path}")
