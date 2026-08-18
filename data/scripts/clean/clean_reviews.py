import json
import os

import pandas as pd

from scripts.paths import DATASETS_DIR

def clean_reviews(trail_id):
    path = os.path.join(DATASETS_DIR, "raw_reviews", f"{trail_id}.json")

    df = pd.read_json(path)
    df = df.rename(columns={"id": "reviewId"})

    # comment_lang is blank for far more reviews than are actually
    # non-English - mostly reviews with no comment text at all (nothing to
    # language-detect), plus some reviews AllTrails just never ran
    # detection on despite having real English text. A strict `== "en-US"`
    # filter throws all of those out along with genuine foreign-language
    # reviews. Keep everything except reviews explicitly tagged as a
    # non-English language instead.
    df = df[df["comment_lang"].isna() | (df["comment_lang"] == "en-US")]

    # A review with no comment has nothing for the condition labeler to
    # work with - drop it here rather than passing it through to
    # enrichment, so label_comment never has to special-case a
    # missing/NaN comment.
    df = df[df["comment"].notna()]

    df["activity"] = df["activity"].apply(lambda a: a["name"] if isinstance(a, dict) else None)

    for col in ["obstacles", "trailConditions"]:
        df[col] = df[col].apply(lambda items: [item["name"] for item in items] if isinstance(items, list) else [])

    df["hasRecording"] = df["associatedRecording"].apply(lambda r: isinstance(r, dict))
    df["recordingId"] = df["associatedRecording"].apply(lambda r: r["id"] if isinstance(r, dict) else None)

    # errors="ignore": pandas only creates a column if at least one review
    # in this trail's raw JSON has it - a trail where every review happens
    # to omit e.g. comment_source (not uncommon for low-review-count
    # trails) means that column just doesn't exist here, which isn't an
    # error, there's nothing to drop.
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
            "ratingAttributes",
            "infoAttributes",
            "commentFeatures",
        ],
        inplace=True,
        errors="ignore",
    )

    new_path = os.path.join(DATASETS_DIR, "cleaned_reviews", f"{trail_id}.json")
    os.makedirs(os.path.dirname(new_path), exist_ok=True)

    records = json.loads(df.to_json(orient="records", force_ascii=False, date_format="iso"))
    with open(new_path, "w", encoding="utf-8") as f:
        json.dump(records, f, indent=2, ensure_ascii=False)

    print(f"saved {len(df)} cleaned reviews to {new_path}")
