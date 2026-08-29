import glob
import json
import os
import sys

import numpy as np
import pandas as pd

from scripts.paths import DATASETS_DIR
from scripts.enrich.enrich_review import CONDITION_CATEGORY_MAP

# server/ has no runtime dependency on data/scripts (see server/app/config.py) -
# the dependency runs the other way here: this offline table-builder imports
# the shared row-flattening logic from server/ rather than the reverse, so
# training-time and live-inference feature assembly can't drift apart
# (constitution Principle II) without both call sites failing to import.
_SERVER_DIR = os.path.join(os.path.dirname(os.path.dirname(DATASETS_DIR)), "server")
if _SERVER_DIR not in sys.path:
    sys.path.insert(0, _SERVER_DIR)
from app.services.feature_flatten import flatten_description, flatten_weather  # noqa: E402

# The canonical set a review's `conditions` list is allowed to contain -
# CONDITION_CATEGORY_MAP's own values, not its keys (several raw spellings
# map to the same canonical category, e.g. "buggy"/"bugs" -> "bugs").
# Enforced again here, not just at enrichment time, because reviews
# enriched before a CONDITION_CATEGORY_MAP change (e.g. when "rocky"/
# "scramble" got dropped from it) still have the old categories baked into
# their saved `conditions` list on disk - re-enriching every trail just to
# purge stale categories would be wasteful when filtering them out here is
# just as correct and free.
VALID_CONDITIONS = set(CONDITION_CATEGORY_MAP.values())

ENRICHED_REVIEWS_DIR = os.path.join(DATASETS_DIR, "enriched_reviews")
DESCRIPTIONS_DIR = os.path.join(DATASETS_DIR, "enriched_descriptions")
OUT_DIR = os.path.join(DATASETS_DIR, "training_table")

# Review fields that are either raw text already mined into `conditions`
# (comment), internal bookkeeping (recordingId/hasRecording), or already
# flattened elsewhere (historicalWeather/conditions handled separately
# below). Terrain now lives on the trail description, not the review - see
# scripts/enrich/enrich_description.py.
REVIEW_DROP_FIELDS = {
    "comment",
    "recordingId",
    "hasRecording",
    "historicalWeather",
    "conditions",
    "difficulty",
    "activity",
    "rating",
    "date"
}


def _clean_scalar(value):
    """Coerce one value to a plain, JSON/CSV-safe Python type: numpy
    scalars -> native int/float, NaN/NaT/pandas-missing -> None, everything
    else passed through unchanged."""
    if isinstance(value, (np.generic,)):
        value = value.item()
    if isinstance(value, float) and np.isnan(value):
        return None
    if value is pd.NaT:
        return None
    if pd.isna(value) if np.isscalar(value) else False:
        return None
    return value


# _flatten_weather/_flatten_terrain/_flatten_description used to live here -
# now imported from server/app/services/feature_flatten.py (see the sys.path
# bootstrap above) so this offline table-builder and the live inference path
# in server/app/services/conditions.py can't drift apart (constitution
# Principle II). surfaceTypes is a list of {label, percentOfSurface,
# totalLength} - picking only the dominant surface would silently throw away
# real mixed-surface trails (e.g. a 55/45 gravel/natural split reads almost
# the same as pure gravel), so flatten_description keeps it as a raw list,
# expanded into one percent column per surface label below (see
# `_add_surface_percentages`), every surface present represented by its
# actual share instead of being reduced to a single winner.


def _load_description(trail_id):
    path = os.path.join(DESCRIPTIONS_DIR, f"{trail_id}.json")
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)


def _flatten_review(review, description_flat, trail_features, surface_types):
    flat = {k: v for k, v in review.items() if k not in REVIEW_DROP_FIELDS}
    flat.update(flatten_weather(review.get("historicalWeather")))
    flat.update(description_flat)

    # Multi-hot/percent columns are filled in afterwards (see
    # build_training_table) once the full vocabulary across every review is
    # known - stash the raw lists here rather than picking columns per-row.
    # Filtered to VALID_CONDITIONS so a stale category left over from an
    # older CONDITION_CATEGORY_MAP (e.g. "rock"/"scramble") can't sneak a
    # column back in.
    flat["_conditions"] = [c for c in (review.get("conditions") or []) if c in VALID_CONDITIONS]
    flat["_trailFeatures"] = trail_features
    flat["_surfaceTypes"] = surface_types
    return flat


def _add_multi_hot(df, list_column, prefix):
    """Turn a column of string-lists (e.g. _conditions: ["muddy", "icy"])
    into one boolean column per distinct value seen anywhere in the
    dataset, then drop the original list column - a fixed multi-hot
    vocabulary discovered from the data, not hardcoded, since AllTrails'
    own obstacle/condition tags aren't a closed set."""
    vocab = sorted({value for values in df[list_column] for value in values})
    for value in vocab:
        column_name = f"{prefix}_{value.replace(' ', '_')}"
        df[column_name] = df[list_column].apply(lambda values: value in values)
    return df.drop(columns=[list_column])


def _add_surface_percentages(df, list_column, prefix):
    """Same idea as `_add_multi_hot`, but for surfaceTypes: one column per
    distinct surface label seen anywhere in the dataset, filled with that
    surface's percentOfSurface for the row (0 if the trail doesn't have
    that surface at all), instead of collapsing a mixed-surface trail down
    to a single dominant winner."""
    vocab = sorted({s["label"] for surfaces in df[list_column] for s in surfaces if s.get("label")})
    for label in vocab:
        column_name = f"{prefix}_{label.replace(' ', '_')}_pct"

        def percent_for(surfaces, label=label):
            for s in surfaces:
                if s.get("label") == label:
                    return s.get("percentOfSurface", 0)
            return 0

        df[column_name] = df[list_column].apply(percent_for)
    return df.drop(columns=[list_column])


def build_training_table(trail_ids=None):
    """Join every enriched review with its trail's description into one
    flat table, ready for a model to consume directly - no nested JSON,
    no raw text, no numpy/pandas-specific types, consistent handling of
    missing values.

    trail_ids: optional list to restrict to specific trails; defaults to
    every trail with an enriched_reviews/{trail_id}.json file.
    """
    if trail_ids is None:
        trail_ids = [
            os.path.splitext(os.path.basename(p))[0]
            for p in glob.glob(os.path.join(ENRICHED_REVIEWS_DIR, "*.json"))
        ]

    rows = []
    for trail_id in trail_ids:
        review_path = os.path.join(ENRICHED_REVIEWS_DIR, f"{trail_id}.json")
        with open(review_path, "r", encoding="utf-8") as f:
            reviews = json.load(f)

        description = _load_description(trail_id)
        description_flat, trail_features, surface_types = flatten_description(description)

        for review in reviews:
            rows.append(_flatten_review(review, description_flat, trail_features, surface_types))

    if not rows:
        raise ValueError(f"no enriched reviews found for trail_ids={trail_ids!r}")

    df = pd.DataFrame(rows)
    df = _add_multi_hot(df, "_conditions", "condition")
    df = _add_multi_hot(df, "_trailFeatures", "feature")
    df = _add_surface_percentages(df, "_surfaceTypes", "trail_surface")

    for column in df.columns:
        if df[column].dtype == object:
            # Only clean genuinely mixed/dirty columns - across-the-board
            # elementwise .apply on every object column is the slow path,
            # but these came from raw JSON via several merge points so
            # None/NaN/numpy scalars can each show up in the same column.
            df[column] = df[column].apply(_clean_scalar)

    return df


def save_training_table(df, name="reviews"):
    os.makedirs(OUT_DIR, exist_ok=True)
    out_path = os.path.join(OUT_DIR, f"{name}.csv")
    df.to_csv(out_path, index=False)
    print(f"saved {len(df)} rows x {len(df.columns)} columns to {out_path}")
    return out_path


# test: python -m scripts.model.build_training_table [trail_id ...]
if __name__ == "__main__":
    args = sys.argv[1:]
    trail_ids = args or None
    table = build_training_table(trail_ids)
    save_training_table(table)
