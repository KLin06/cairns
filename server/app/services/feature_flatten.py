"""Shared row-flattening logic (constitution Principle II - Feature Parity):
the *only* place a single review/request row gets turned into the
weather_d*/terrain_*/trail_* columns `condition_models.joblib` was trained
on. Used directly by the live inference path (app/services/conditions.py)
and imported by data/scripts/model/build_training_table.py and
data/scripts/enrich/enrich_review.py (the offline training/enrichment
pipeline) - a one-directional dependency (data/scripts -> server), not the
reverse: server/ has no runtime dependency on data/scripts by design (see
app/config.py), so this module is pure pandas/stdlib, no FastAPI/pydantic,
importable from data/scripts' own venv without pulling in the API stack.

Keep this module in sync with itself, not two copies of it - if either
build_training_table.py or conditions.py needs different row-flattening
behavior, that's a sign the two have actually diverged and needs a real
decision, not a silent copy-paste fix in just one place.
"""

HISTORY_DAYS = 7  # weather_d0 (hike day) .. weather_d7 (a week before)

# daily weather field -> short column-name stub. precipitation_sum is
# deliberately excluded: it's just rain_sum + snowfall_sum's water
# equivalent (verified against real data), so keeping it alongside rain/snow
# would be pure redundant information, not an extra signal.
WEATHER_FIELDS = {
    "temperature_2m_max": "tempMax",
    "temperature_2m_min": "tempMin",
    "rain_sum": "rain",
    "snowfall_sum": "snow",
    "windspeed_10m_max": "windMax",
}


def flatten_weather(daily_records, history_days=HISTORY_DAYS):
    """Keep each day of the history_days lead-up as its own columns
    (weather_d0_* = the target day itself, weather_d7_* = a week before)
    instead of collapsing the week into one aggregate - rain the day before
    makes for a muddy trail in a way rain a week before (likely already
    drained/dried) doesn't, and averaging the two erases that distinction.

    daily_records is date-sorted ascending, oldest first, target day last -
    indexed here from the end so "d0" always means the target day regardless
    of how many records came back."""
    daily_records = daily_records or []
    flat = {}
    for day_offset in range(history_days + 1):
        index_from_end = day_offset + 1
        record = daily_records[-index_from_end] if index_from_end <= len(daily_records) else {}
        for api_field, stub in WEATHER_FIELDS.items():
            flat[f"weather_d{day_offset}_{stub}"] = record.get(api_field)
    return flat


# Lookback window (days before the target day, the day itself excluded - see
# antecedent_precip_index) for the antecedent precipitation index. Wider than
# HISTORY_DAYS on purpose: HISTORY_DAYS's per-day columns are meant to
# distinguish "rained yesterday" from "rained a week ago", but neither they
# nor a single day's reading can tell a trail that's been saturated for two
# weeks apart from one that just had a single wet day - that's what this is
# for. 14 days is a starting point (roughly matches typical soil-drainage
# timescales), not a validated constant.
ANTECEDENT_DAYS = 14

# Per-day decay applied going backwards from the target day (see
# antecedent_precip_index) - a storm 1-2 days back should count for much more
# than one 2 weeks back. 0.9/day gives roughly a 6-7 day half-life; not tuned
# against real data yet, just a plausible starting point.
ANTECEDENT_DECAY = 0.9


def antecedent_precip_index(daily_records):
    """Exponentially-decayed sum of rain + snow (water-equivalent) over the
    ANTECEDENT_DAYS before the target day, each day weighted
    ANTECEDENT_DECAY^(days_before - 1) so a storm 1-2 days back counts far
    more than one from two weeks back - a rough Antecedent Precipitation
    Index, standard in hydrology for approximating soil saturation from a
    rainfall time series without a real soil-moisture model.

    daily_records is date-sorted ascending (oldest first), covering the
    ANTECEDENT_DAYS immediately before the target day and NOT including the
    target day itself (already fully represented by weather_d0_rain/snow -
    including it here would double-count it)."""
    index = 0.0
    for days_before, record in enumerate(reversed(daily_records or []), start=1):
        rain = record.get("rain_sum") or 0
        snow = record.get("snowfall_sum") or 0
        index += (rain + snow) * (ANTECEDENT_DECAY ** (days_before - 1))
    return round(index, 3)


# Trail-description fields that carry no predictive signal (raw text/media/
# ids) or are constant across every trail (worstRating/bestRating are always
# AllTrails' fixed 0-5 scale) - not worth a column each.
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


def flatten_terrain(terrain):
    """terrainData is {"rock": {...} | None, "soil": {...} | None} - reduced
    to just the four fields that actually carry model signal for trail
    conditions:
    - rockSlipRisk: wet-rock traction rating
    - soilDrainageRank: ordinal 0 (best drained) - 6 (worst, most mud-prone)
    - soilTextureMudPotential: ordinal 0-2 mud potential from soil texture
    - soilTextureGroup: broad texture class (clay/silt/loam/sand/organic/rock)
    Everything else (rockType/rockDescription/geologicEra/soilName/
    parentMaterial/etc.) is identifying/descriptive detail without direct
    predictive value, so it's dropped here."""
    terrain = terrain or {}
    rock = terrain.get("rock") or {}
    soil = terrain.get("soil") or {}
    return {
        "terrain_rockSlipRisk": rock.get("rockSlipRisk"),
        "terrain_soilDrainageRank": soil.get("drainageRank"),
        "terrain_soilTextureMudPotential": soil.get("textureMudPotential"),
        "terrain_soilTextureGroup": soil.get("textureGroup"),
    }


def flatten_description(description):
    """Returns (flat, features, surface_types): `flat` is every remaining
    top-level description field prefixed `trail_` (lat/lng/length/
    difficultyRating survive this - DESCRIPTION_DROP_FIELDS doesn't touch
    them) plus the four terrain_* fields from flatten_terrain; `features`
    and `surface_types` are popped out as raw lists for the caller to expand
    into feature_*/trail_surface_*_pct columns separately (training expands
    them against a data-discovered vocabulary; live inference expands them
    against the trained model's own fixed vocabulary - different enough
    procedures that they're not part of this shared function)."""
    terrain = description.get("terrainData")
    flat = {f"trail_{k}": v for k, v in description.items() if k not in DESCRIPTION_DROP_FIELDS and k != "terrainData"}
    features = flat.pop("trail_features", None) or []
    surface_types = flat.pop("trail_surfaceTypes", None) or []
    flat.update(flatten_terrain(terrain))
    return flat, features, surface_types
