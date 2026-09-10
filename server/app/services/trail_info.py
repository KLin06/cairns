import json
import os

from fastapi import HTTPException
from psycopg2.extras import RealDictCursor

from app.config import CLEANED_REVIEWS_DIR, ENRICHED_DESCRIPTIONS_DIR
from app.schemas import SurfaceType, Terrain, TrailInfo
from app.services import data_store
from db.connection import get_connection

# What fraction of a trail's reviews need to mention "Scramble" (AllTrails'
# own obstacle/trailCondition tag, not a model-derived category - see
# CONDITION_CATEGORY_MAP in data/scripts/enrich/enrich_review.py, which no
# longer maps "scramble" to anything, so it can't be read off a review's
# processed `conditions` list anymore) before the trail counts as having
# scrambling. Open question in APP_SPEC.md - this is a first-pass guess,
# not a tuned value.
SCRAMBLE_THRESHOLD = 0.02


def _compute_has_scrambling(trail_id):
    path = os.path.join(CLEANED_REVIEWS_DIR, f"{trail_id}.json")
    if not os.path.exists(path):
        return False

    with open(path, "r", encoding="utf-8") as f:
        reviews = json.load(f)
    if not reviews:
        return False

    mentions = sum(
        1
        for r in reviews
        if any(tag.lower() == "scramble" for tag in (r.get("obstacles", []) + r.get("trailConditions", [])))
    )
    return (mentions / len(reviews)) >= SCRAMBLE_THRESHOLD


def _as_int(value):
    return None if value is None else int(value)


def _as_float(value):
    return None if value is None else float(value)


def derive_trail_record(trail_id: str) -> dict | None:
    """Plain-value equivalent of get_trail_info(), for callers (the backfill
    script) that need the raw derived fields - including latitude/longitude,
    which aren't part of TrailInfo since the API has no use for them there -
    without going through get_trail_info()'s HTTPException/Pydantic-response
    shape. Returns None (not an exception) when the trail has no enriched
    description at all, since that's a legitimate "not eligible" signal for
    a caller like the backfill, not necessarily an error."""
    path = os.path.join(ENRICHED_DESCRIPTIONS_DIR, f"{trail_id}.json")
    if not os.path.exists(path):
        return None
    with open(path, "r", encoding="utf-8") as f:
        description = json.load(f)

    terrain_data = description.get("terrainData") or {}
    rock = terrain_data.get("rock") or {}
    soil = terrain_data.get("soil") or {}
    surface_types = description.get("surfaceTypes") or None
    features = description.get("features") or None
    images = description.get("images") or []

    return {
        "trail_id": str(trail_id),
        "name": description.get("name"),
        "latitude": _as_float(description.get("latitude")),
        "longitude": _as_float(description.get("longitude")),
        # Source JSON is inconsistent about numeric types (e.g. difficultyRating
        # sometimes arrives as a string) - TrailInfo's Pydantic fields coerce
        # this silently; derive_trail_record does it explicitly so a plain
        # dict comparison (upsert_trail's change detection) isn't fooled by
        # e.g. 3 vs "3" into treating unchanged data as changed.
        "difficulty_rating": _as_int(description.get("difficultyRating")),
        "length_meters": _as_float(description.get("length")),
        "duration_minutes": _as_int(description.get("durationMinutes")),
        "has_scrambling": _compute_has_scrambling(trail_id),
        "rock_slip_risk": rock.get("rockSlipRisk"),
        "soil_drainage": soil.get("drainage"),
        # Model-only fields (server/app/services/feature_flatten.py's
        # flatten_terrain) - distinct from soil_drainage above, which is a
        # different source field ("drainage") used for display, not the
        # model. Backfilled here so conditions.py's live read-path never
        # needs enriched_descriptions/{trail_id}.json directly.
        "soil_drainage_rank": _as_int(soil.get("drainageRank")),
        "soil_texture_mud_potential": _as_int(soil.get("textureMudPotential")),
        "soil_texture_group": soil.get("textureGroup"),
        "surface_types": surface_types,
        "features": features,
        # First of the scraped AllTrails photo URLs, if any - selective field
        # storage (constitution IX) means one representative image, not the
        # whole gallery array.
        "image_url": images[0] if images else None,
        "area_name": description.get("areaName"),
    }


def get_trail_info(trail_id: str) -> TrailInfo:
    """Reads the trails table (specs/002-trail-data-storage-schema), populated
    by server/db/backfill.py from the same enriched_descriptions/cleaned_reviews
    files derive_trail_record() above reads directly - that function stays
    file-based because the backfill script still needs it as its own source
    of truth; this one is the live read-path, migrated off flat files."""
    if data_store.enabled():
        row = data_store.get_trail(trail_id)
    else:
        conn = get_connection()
        try:
            with conn.cursor(cursor_factory=RealDictCursor) as cur:
                cur.execute("SELECT * FROM trails WHERE trail_id = %s", (str(trail_id),))
                row = cur.fetchone()
        finally:
            conn.close()

    if row is None:
        raise HTTPException(
            status_code=404,
            detail=f"trail {trail_id!r} has no enriched description - has it been through the enrich pipeline stage?",
        )

    return TrailInfo(
        trailId=row["trail_id"],
        name=row["name"],
        difficultyRating=row["difficulty_rating"],
        lengthMeters=row["length_meters"],
        durationMinutes=row["duration_minutes"],
        hasScrambling=row["has_scrambling"],
        surfaceTypes=[
            SurfaceType(label=s.get("label"), percentOfSurface=s.get("percentOfSurface"))
            for s in (row["surface_types"] or [])
        ],
        terrain=Terrain(
            rockSlipRisk=row["rock_slip_risk"],
            soilDrainage=row["soil_drainage"],
        ),
        features=row["features"] or [],
        imageUrl=row["image_url"],
        areaName=row["area_name"],
    )
