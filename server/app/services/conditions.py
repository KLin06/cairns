import io
import logging
import threading
import time
from datetime import date as date_cls
from datetime import timedelta

import boto3
import joblib
import pandas as pd
from botocore.exceptions import BotoCoreError, ClientError
from fastapi import HTTPException
from psycopg2.extras import RealDictCursor

from app.config import MODEL_S3_BUCKET, MODEL_S3_KEY
from app.schemas import ConditionResult, ConditionsConfidence, ConditionsResponse, ValidRange, WeatherErrorDetail
from app.services.activity import get_trail_activity
from app.services.feature_flatten import ANTECEDENT_DAYS, antecedent_precip_index, flatten_description, flatten_weather
from app.services.open_meteo_client import MAX_FORECAST_DAYS, fetch_forecast_range
from db.connection import get_connection

# train_model.py's CATEGORICAL_COLUMNS - a training-config fact (which
# columns HistGradientBoostingClassifier needs as pandas `category` dtype),
# not row-flattening logic, so it's not worth pulling train_model.py's own
# sklearn-training imports into server/ for two strings. Keep in sync with
# data/scripts/model/train_model.py's CATEGORICAL_COLUMNS by hand.
CATEGORICAL_COLUMNS = ["terrain_rockSlipRisk", "terrain_soilTextureGroup"]

# spec.md Assumptions: "a reasonable low-data cutoff (e.g. under ~20
# historical reviews reads as 'limited data')... a tuning detail, not a
# product decision requiring sign-off."
LIMITED_DATA_THRESHOLD = 20

_CACHE: dict[str, dict] = {}
_CACHE_TTL_SECONDS = 30 * 60  # mirrors weather.py's cache window

# The Day Selection strip (US2) fans out one conditions request per window
# date (~16 at once) on trail-open - without per-trail locking, every one
# of those would independently miss the still-empty cache and fire its own
# Open-Meteo fetch (observed directly: a cold 16-way burst took 14s+ per
# request before this fix, vs <1s once warm). One lock per trail_id so only
# the first concurrent request for a given trail actually hits Open-Meteo;
# the rest block briefly and then read the now-warm cache.
_TRAIL_LOCKS_GUARD = threading.Lock()
_TRAIL_LOCKS: dict[str, threading.Lock] = {}

_MODEL_BUNDLE: dict | None = None

_logger = logging.getLogger(__name__)


def _error(status_code: int, error_type: str, message: str, valid_range: ValidRange | None = None) -> HTTPException:
    detail = WeatherErrorDetail(errorType=error_type, message=message, validRange=valid_range)
    return HTTPException(status_code=status_code, detail=detail.model_dump(by_alias=True))


def _fetch_model_bundle_from_s3() -> dict:
    """Downloads condition_models.joblib from S3 (see
    specs/007-docker-containerization/contracts/s3-model-object.md) and
    deserializes it from an in-memory buffer - no local file ever hits disk.
    version comes from the S3 object's LastModified, not local file mtime
    (a freshly-downloaded file's mtime would just be "now", not the date the
    model was actually trained - see research.md section 1). Raises the same
    structured HTTPException shape as the rest of this module (_error) so a
    fetch/deserialize failure surfaces as a clear API error (FR-009) instead
    of an unhandled 500."""
    if not MODEL_S3_BUCKET or not MODEL_S3_KEY:
        _logger.error("MODEL_S3_BUCKET and MODEL_S3_KEY must both be set to load the conditions model")
        raise _error(503, "model_unavailable", "conditions model is not configured (missing S3 bucket/key)")

    s3 = boto3.client("s3")
    try:
        response = s3.get_object(Bucket=MODEL_S3_BUCKET, Key=MODEL_S3_KEY)
    except ClientError as exc:
        error_code = exc.response.get("Error", {}).get("Code")
        _logger.error("failed to fetch model from s3://%s/%s: %s", MODEL_S3_BUCKET, MODEL_S3_KEY, error_code or exc)
        raise _error(503, "model_unavailable", f"could not fetch conditions model from S3 ({error_code or exc})") from exc
    except BotoCoreError as exc:
        _logger.error("failed to reach S3 for s3://%s/%s: %s", MODEL_S3_BUCKET, MODEL_S3_KEY, exc)
        raise _error(503, "model_unavailable", f"could not reach S3 to fetch conditions model ({exc})") from exc

    version = response["LastModified"].date().isoformat()
    body = response["Body"].read()
    try:
        bundle = joblib.load(io.BytesIO(body))
    except Exception as exc:
        _logger.error("model artifact at s3://%s/%s failed to deserialize: %s", MODEL_S3_BUCKET, MODEL_S3_KEY, exc)
        raise _error(500, "model_corrupted", "conditions model artifact in S3 is corrupted or unreadable") from exc

    bundle["version"] = version
    return bundle


def _load_model_bundle() -> dict:
    """Loaded once per process (not per-request, per the original TODO) and
    cached in this module-level global - {"models": {condition: fitted
    model}, "features": [...], "thresholds": {condition: float}, "version":
    ...} - fetched from S3 on first call, then reused for the rest of the
    process's lifetime (FR-005: at most one S3 fetch per process)."""
    global _MODEL_BUNDLE
    if _MODEL_BUNDLE is None:
        _MODEL_BUNDLE = _fetch_model_bundle_from_s3()
    return _MODEL_BUNDLE


def _resolve_and_validate_date(date_str: str) -> date_cls:
    target = date_cls.fromisoformat(date_str)
    today = date_cls.today()
    # Same bound as weather.py's _resolve_and_validate_dates: MAX_FORECAST_DAYS
    # is a day *count* starting from today, so the furthest valid offset is
    # MAX_FORECAST_DAYS - 1, not MAX_FORECAST_DAYS itself.
    horizon_end = today + timedelta(days=MAX_FORECAST_DAYS - 1)
    if target < today or target > horizon_end:
        raise _error(
            422,
            "invalid_date_range",
            f"requested date {date_str!r} is outside the valid forecast range",
            valid_range=ValidRange(**{"from": today.isoformat(), "to": horizon_end.isoformat()}),
        )
    return target


def _load_description(trail_id: str) -> dict:
    """Reads the trails table (specs/002-trail-data-storage-schema) instead
    of enriched_descriptions/{trail_id}.json directly, reconstructing a dict
    shaped exactly like the old raw description JSON - flatten_description()
    (shared with build_training_table.py, constitution Principle II) reads
    specific top-level/terrainData keys and is not itself touched by this
    migration. soil_drainage_rank/soil_texture_mud_potential/
    soil_texture_group (migration 0004) are the trails-table columns added
    specifically because flatten_terrain needs them and the pre-existing
    soil_drainage column is a different source field ("drainage"), not
    reusable here."""
    conn = get_connection()
    try:
        with conn.cursor(cursor_factory=RealDictCursor) as cur:
            cur.execute("SELECT * FROM trails WHERE trail_id = %s", (str(trail_id),))
            row = cur.fetchone()
    finally:
        conn.close()

    if row is None:
        raise _error(
            404,
            "trail_unavailable",
            f"trail {trail_id!r} has no enriched description - has it been through the enrich pipeline stage?",
        )

    if row["latitude"] is None or row["longitude"] is None:
        raise _error(404, "trail_unavailable", f"trail {trail_id!r} has no location on record")

    return {
        "latitude": row["latitude"],
        "longitude": row["longitude"],
        "length": row["length_meters"],
        "difficultyRating": row["difficulty_rating"],
        "features": row["features"] or [],
        "surfaceTypes": row["surface_types"] or [],
        "terrainData": {
            "rock": {"rockSlipRisk": row["rock_slip_risk"]},
            "soil": {
                "drainageRank": row["soil_drainage_rank"],
                "textureMudPotential": row["soil_texture_mud_potential"],
                "textureGroup": row["soil_texture_group"],
            },
        },
    }


def _classify_upstream_error(exc: Exception) -> HTTPException:
    status = getattr(getattr(exc, "response", None), "status_code", None)
    if status == 429:
        return _error(503, "upstream_rate_limited", "weather provider is rate-limiting requests; try again shortly")
    return _error(502, "upstream_unavailable", "weather provider returned an unexpected error")


def _cached_window(trail_id: str) -> dict[str, dict] | None:
    entry = _CACHE.get(trail_id)
    if entry is not None and (time.time() - entry["fetched_at"]) < _CACHE_TTL_SECONDS:
        return entry["by_date"]
    return None


def _get_weather_window(trail_id: str, lat: float, lng: float) -> dict[str, dict]:
    """{date_str: daily_record} covering [today - ANTECEDENT_DAYS, today +
    MAX_FORECAST_DAYS - 1] - wide enough to serve weather_d0-d7 + the
    antecedent-precipitation window behind *any* validly-requested date, in
    one upstream call per trail (research.md decision 5) rather than one
    call per requested date."""
    cached = _cached_window(trail_id)
    if cached is not None:
        return cached

    with _TRAIL_LOCKS_GUARD:
        lock = _TRAIL_LOCKS.setdefault(trail_id, threading.Lock())

    with lock:
        # Re-check now that the lock is held - another thread may have
        # already populated the cache while this one was waiting.
        cached = _cached_window(trail_id)
        if cached is not None:
            return cached

        today = date_cls.today()
        start = today - timedelta(days=ANTECEDENT_DAYS)
        end = today + timedelta(days=MAX_FORECAST_DAYS - 1)
        try:
            records = fetch_forecast_range(lat, lng, start.isoformat(), end.isoformat())
        except Exception as exc:
            raise _classify_upstream_error(exc) from exc

        by_date = {r["date"]: r for r in records}
        _CACHE[trail_id] = {"fetched_at": time.time(), "by_date": by_date}
        return by_date


def _target_day_records(by_date: dict[str, dict], target: date_cls) -> list[dict]:
    """Date-sorted ascending records for [target - ANTECEDENT_DAYS, target]
    (target last) - covers both flatten_weather's 8-day tail
    (weather_d0..d7) and, via records[:-1], antecedent_precip_index's
    14-day window immediately before target. A day missing from the
    upstream response (shouldn't happen inside the fetched window, but
    tolerated the same way flatten_weather/antecedent_precip_index already
    tolerate a short historicalWeather list) becomes {}."""
    dates = [target - timedelta(days=n) for n in range(ANTECEDENT_DAYS, -1, -1)]
    return [by_date.get(d.isoformat(), {}) for d in dates]


FEATURE_PREFIX = "feature_"
SURFACE_PREFIX = "trail_surface_"
SURFACE_SUFFIX = "_pct"


def _feature_columns(model_features: list[str], trail_features: list[str]) -> dict[str, bool]:
    """feature_* columns are a fixed vocabulary baked into the trained
    model (research.md decision 3), not rediscovered per request - test
    this trail's own `features` list against each column the model actually
    has, same naming convention _add_multi_hot used at training time
    (spaces -> underscores). Absent from the trail's own list -> False,
    matching training's multi-hot defaulting."""
    normalized = {f.replace(" ", "_") for f in (trail_features or [])}
    return {col: (col[len(FEATURE_PREFIX) :] in normalized) for col in model_features if col.startswith(FEATURE_PREFIX)}


def _surface_pct_columns(model_features: list[str], surface_types: list[dict]) -> dict[str, float]:
    """Same idea as _feature_columns but for trail_surface_*_pct - a
    surface absent from this trail's own surfaceTypes list defaults to 0,
    matching training's _add_surface_percentages defaulting."""
    pct_by_label = {}
    for s in surface_types or []:
        label = s.get("label")
        if label:
            pct_by_label[label.replace(" ", "_")] = s.get("percentOfSurface") or 0
    return {
        col: pct_by_label.get(col[len(SURFACE_PREFIX) : -len(SURFACE_SUFFIX)], 0)
        for col in model_features
        if col.startswith(SURFACE_PREFIX) and col.endswith(SURFACE_SUFFIX)
    }


def _assemble_feature_row(target: date_cls, description: dict, by_date: dict[str, dict], model_bundle: dict) -> pd.DataFrame:
    """One-row DataFrame with exactly model_bundle["features"] as columns,
    in that order, dtypes matching train_model.py's CATEGORICAL_COLUMNS -
    the live-inference half of constitution Principle II. Every value here
    comes from the same shared flatten_* functions (or the same fixed-vocab
    reindex logic) build_training_table.py uses, so this can't silently
    drift from what the model was actually trained on."""
    records = _target_day_records(by_date, target)
    weather_flat = flatten_weather(records)
    antecedent = antecedent_precip_index(records[:-1])
    description_flat, trail_features, surface_types = flatten_description(description)

    row = {
        "dayOfYear": target.timetuple().tm_yday,
        "antecedentPrecipIndex": antecedent,
        **weather_flat,
        **description_flat,
        **_feature_columns(model_bundle["features"], trail_features),
        **_surface_pct_columns(model_bundle["features"], surface_types),
    }

    df = pd.DataFrame([row]).reindex(columns=model_bundle["features"])
    for col in CATEGORICAL_COLUMNS:
        if col in df.columns:
            df[col] = df[col].astype("category")
    return df


def _confidence(trail_id: str) -> ConditionsConfidence:
    """Sourced from trail_activity.total_reviews (spec.md Assumptions). A
    trail with no activity row at all (never backfilled, or zero cleaned
    reviews) reads the same as reviewCount=0 rather than blocking the whole
    prediction - conditions doesn't require review history for the
    *specific* trail beyond what the model was trained on (see spec.md's
    Edge Cases)."""
    try:
        review_count = get_trail_activity(trail_id).totalReviews
    except HTTPException as exc:
        if exc.status_code == 404:
            review_count = 0
        else:
            raise
    return ConditionsConfidence(reviewCount=review_count, limitedData=review_count < LIMITED_DATA_THRESHOLD)


def get_trail_conditions(trail_id: str, date: str) -> ConditionsResponse:
    target = _resolve_and_validate_date(date)
    description = _load_description(trail_id)

    by_date = _get_weather_window(trail_id, description["latitude"], description["longitude"])
    if target.isoformat() not in by_date:
        raise _error(502, "upstream_unavailable", "weather provider returned an incomplete forecast window")

    model_bundle = _load_model_bundle()
    row = _assemble_feature_row(target, description, by_date, model_bundle)

    conditions: dict[str, ConditionResult] = {}
    for condition_key, model in model_bundle["models"].items():
        probability = float(model.predict_proba(row)[:, 1][0])
        name = condition_key[len("condition_") :] if condition_key.startswith("condition_") else condition_key
        conditions[name] = ConditionResult(probability=probability, predicted=probability >= model_bundle["thresholds"][condition_key])

    return ConditionsResponse(
        trailId=str(trail_id),
        date=target.isoformat(),
        conditions=conditions,
        modelVersion=model_bundle["version"],
        confidence=_confidence(trail_id),
    )
