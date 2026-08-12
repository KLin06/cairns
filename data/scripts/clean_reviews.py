import json
import os

import pandas as pd

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
DATA_DIR = os.path.dirname(SCRIPT_DIR)
path = os.path.join(DATA_DIR, "raw_reviews", "the_crack_trail_reviews.json")

df = pd.read_json(path)
df.set_index("id", inplace=True)

df = df[df["comment_lang"] == "en-US"]

# Flatten nested fields into plain, analysis-friendly values instead of
# dropping them outright: a column of dicts/lists can't be grouped or
# counted on directly.
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

new_path = os.path.join(DATA_DIR, "cleaned_reviews", "the_crack_trail_reviews_cleaned.json")

# pandas' to_json(indent=...) pads empty lists/dicts with a stray blank
# line. Let pandas handle date serialization, then hand the compact JSON
# string off to the stdlib json module for clean pretty-printing.
records = json.loads(df.to_json(orient="records", force_ascii=False, date_format="iso"))
with open(new_path, "w", encoding="utf-8") as f:
    json.dump(records, f, indent=2, ensure_ascii=False)

print(f"saved {len(df)} cleaned reviews to {new_path}")
