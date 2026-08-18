import json
import os

from fastapi import HTTPException

from app.config import CLEANED_REVIEWS_DIR, ENRICHED_DESCRIPTIONS_DIR
from app.schemas import SurfaceType, Terrain, TrailInfo

# What fraction of a trail's reviews need to mention "Scramble" (AllTrails'
# own obstacle/trailCondition tag, not a model-derived category - see
# CONDITION_CATEGORY_MAP in data/scripts/enrich/enrich_review.py, which no
# longer maps "scramble" to anything, so it can't be read off a review's
# processed `conditions` list anymore) before the trail counts as having
# scrambling. Open question in APP_SPEC.md - this is a first-pass guess,
# not a tuned value.
SCRAMBLE_THRESHOLD = 0.02


def _load_json(path, not_found_message):
    if not os.path.exists(path):
        raise HTTPException(status_code=404, detail=not_found_message)
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)


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


def get_trail_info(trail_id: str) -> TrailInfo:
    path = os.path.join(ENRICHED_DESCRIPTIONS_DIR, f"{trail_id}.json")
    description = _load_json(
        path, f"trail {trail_id!r} has no enriched description - has it been through the enrich pipeline stage?"
    )

    terrain_data = description.get("terrainData") or {}
    rock = terrain_data.get("rock") or {}
    soil = terrain_data.get("soil") or {}

    return TrailInfo(
        trailId=str(trail_id),
        name=description.get("name"),
        difficultyRating=description.get("difficultyRating"),
        lengthMeters=description.get("length"),
        durationMinutes=description.get("durationMinutes"),
        hasScrambling=_compute_has_scrambling(trail_id),
        surfaceTypes=[
            SurfaceType(label=s.get("label"), percentOfSurface=s.get("percentOfSurface"))
            for s in (description.get("surfaceTypes") or [])
        ],
        terrain=Terrain(
            rockSlipRisk=rock.get("rockSlipRisk"),
            soilDrainage=soil.get("drainage"),
        ),
        features=description.get("features") or [],
    )
