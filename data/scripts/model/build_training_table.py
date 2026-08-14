import glob
import json
import os
import sys

import numpy as np
import pandas as pd

from scripts.paths import DATASETS_DIR
from scripts.enrich.enrich_review import HISTORY_DAYS

ENRICHED_REVIEWS_DIR = os.path.join(DATASETS_DIR, "enriched_reviews")
DESCRIPTIONS_DIR = os.path.join(DATASETS_DIR, "enriched_descriptions")
OUT_DIR = os.path.join(DATASETS_DIR, "training_table")

# Trail-description fields that carry no predictive signal (raw text/media/
# ids) or are constant across every trail (worstRating/bestRating are
# always AllTrails' fixed 0-5 scale) - not worth a column each.
DESCRIPTION_DROP_FIELDS = {
    "trailId",
    "trailSlug",
    "name",
    "description",
    "images",
    "worstRating",
    "bestRating",
    "ratingValue",
    "reviewCount",
    "durationMinutes",
    "areaName",
    "popularity",
    "addressLocality",
}

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


# daily weather field -> short column-name stub
_WEATHER_FIELDS = {
    "temperature_2m_max": "tempMax",
    "temperature_2m_min": "tempMin",
    "precipitation_sum": "precip",
    "rain_sum": "rain",
    "snowfall_sum": "snow",
    "windspeed_10m_max": "windMax",
}


def _flatten_weather(daily_records):
    """Keep each day of the HISTORY_DAYS lead-up as its own columns
    (weather_d0_* = the hike day itself, weather_d7_* = a week before)
    instead of collapsing the week into one aggregate - rain the day
    before a hike makes for a muddy trail in a way rain a week before
    (likely already drained/dried) doesn't, and averaging the two together
    erases exactly that distinction.

    historicalWeather (see fetch_historical_weather) is date-sorted
    ascending, oldest first, hike day last - indexed here from the end so
    "d0" always means the hike day regardless of how many records came
    back (fewer than HISTORY_DAYS+1 near the ERA5 archive lag, for
    instance)."""
    daily_records = daily_records or []
    flat = {}
    for day_offset in range(HISTORY_DAYS + 1):
        index_from_end = day_offset + 1
        record = daily_records[-index_from_end] if index_from_end <= len(daily_records) else {}
        for api_field, stub in _WEATHER_FIELDS.items():
            flat[f"weather_d{day_offset}_{stub}"] = record.get(api_field)
    return flat


def _flatten_terrain(terrain):
    """terrainData is {"rock": {...} | None, "soil": {...} | None} (see
    scripts/enrich/enrich_description.py) - reduced to just the four
    fields that actually carry model signal for trail conditions, not
    every raw/derived terrain field:
    - rockSlipRisk: wet-rock traction rating (rock_classification.py)
    - soilDrainageRank: ordinal 0 (best drained) - 6 (worst, most
      mud-prone)
    - soilTextureMudPotential: ordinal 0-2 mud potential from soil texture
    - soilTextureGroup: broad texture class (clay/silt/loam/sand/organic/
      rock)
    Everything else (rockType/rockDescription/geologicEra/soilName/
    parentMaterial/etc.) is identifying/descriptive detail without direct
    predictive value, so it's dropped here rather than carried into the
    training table."""
    terrain = terrain or {}
    rock = terrain.get("rock") or {}
    soil = terrain.get("soil") or {}
    return {
        "terrain_rockSlipRisk": rock.get("rockSlipRisk"),
        "terrain_soilDrainageRank": soil.get("drainageRank"),
        "terrain_soilTextureMudPotential": soil.get("textureMudPotential"),
        "terrain_soilTextureGroup": soil.get("textureGroup"),
    }


def _flatten_description(description):
    terrain = description.get("terrainData")
    flat = {
        f"trail_{k}": v
        for k, v in description.items()
        if k not in DESCRIPTION_DROP_FIELDS and k != "terrainData"
    }
    features = flat.pop("trail_features", None) or []
    # surfaceTypes is a list of {label, percentOfSurface, totalLength} -
    # picking only the dominant surface would silently throw away real
    # mixed-surface trails (e.g. a 55/45 gravel/natural split reads almost
    # the same as pure gravel). Kept as a raw list here and expanded into
    # one percent column per surface label later (see
    # `_add_surface_percentages` in build_training_table), so every surface
    # present is represented by its actual share instead of being reduced
    # to a single winner.
    surface_types = flat.pop("trail_surfaceTypes", None) or []
    flat.update(_flatten_terrain(terrain))
    return flat, features, surface_types


def _load_description(trail_id):
    path = os.path.join(DESCRIPTIONS_DIR, f"{trail_id}.json")
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)


def _flatten_review(review, description_flat, trail_features, surface_types):
    flat = {k: v for k, v in review.items() if k not in REVIEW_DROP_FIELDS}
    flat.update(_flatten_weather(review.get("historicalWeather")))
    flat.update(description_flat)

    # Multi-hot/percent columns are filled in afterwards (see
    # build_training_table) once the full vocabulary across every review is
    # known - stash the raw lists here rather than picking columns per-row.
    flat["_conditions"] = review.get("conditions") or []
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
        description_flat, trail_features, surface_types = _flatten_description(description)

        for review in reviews:
            rows.append(_flatten_review(review, description_flat, trail_features, surface_types))

    if not rows:
        raise ValueError(f"no enriched reviews found for trail_ids={trail_ids!r}")

    df = pd.DataFrame(rows)
    df = _add_multi_hot(df, "_conditions", "condition")
    df = _add_multi_hot(df, "_trailFeatures", "feature")
    df = _add_surface_percentages(df, "_surfaceTypes", "trail_surface")

    # date columns arrive as strings (JSON has no native datetime) - parse
    # once so downstream code gets real Timestamps instead of re-parsing
    # ad hoc, then drop the tz AllTrails always reports as UTC-labelled
    # local time, which isn't meaningful for a per-trail weather join.
    df["date"] = pd.to_datetime(df["date"], utc=True).dt.tz_localize(None)

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
    print(table.columns)
    save_training_table(table)
