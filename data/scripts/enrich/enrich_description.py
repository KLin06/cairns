import json
import os
import sys

from scripts.paths import DATASETS_DIR
from scripts.enrich.terrain.bedrock import fetch_rock_type
from scripts.enrich.terrain.soil import fetch_soil_type
from scripts.enrich.terrain.rock_classification import classify_rock
from scripts.enrich.terrain.soil_codes import decode_texture, decode_drainage, decode_stoniness, classify_texture


def _summarize_rock(features):
    """Pull the fields that actually matter for the model out of the raw
    ArcGIS attribute dump (which also carries OBJECTID, stratigraphy codes,
    etc. that are useless as model features). None when the point falls
    outside mapped bedrock coverage (empty feature list).

    ROCKTYPE_P is free text ("Limestone, dolostone, shale") - too high-
    cardinality to use directly, so it's also run through
    `classify_rock` (see rock_classification.py) to get a small set of
    lithology categories plus a wet-rock slip-risk rating."""
    if not features:
        return None
    rock = features[0]
    classification = classify_rock(rock.get("ROCKTYPE_P"))
    return {
        "rockType": rock.get("UNITNAME_P"),
        "rockDescription": rock.get("ROCKTYPE_P"),
        "geologicProvince": rock.get("PROVINCE_P"),
        "geologicEra": rock.get("ERA_P"),
        "rockCategories": classification["categories"],
        "rockSlipRisk": classification["slipRisk"],
    }


def _summarize_soil(features):
    """Same idea as `_summarize_rock`: keep only the soil attributes with
    predictive value for trail conditions (texture/drainage/slope/stoniness)
    out of the ~50 raw survey fields. None outside the southern-Ontario
    soil survey coverage area (empty feature list).

    ATEXTURE1/DRAINAGE1/STONINESS1 arrive as short coded abbreviations
    (standard Canadian soil-survey codes, not ArcGIS domains - see
    soil_codes.py) - decoded here into readable labels. Texture is also
    run through `classify_texture` to fold its 29 codes down into a
    handful of broad groups (clay/silt/loam/sand/organic/rock) plus a
    `textureMudPotential` score, and drainage gets an ordinal
    `drainageRank` (0 = best drained/least mud-prone, 6 = worst/most
    mud-prone) - drainage and texture are the two fields most directly
    tied to "does this trail turn to mud after rain"."""
    if not features:
        return None
    soil = features[0]
    drainage = decode_drainage(soil.get("DRAINAGE1"))
    texture_class = classify_texture(soil.get("ATEXTURE1"))
    return {
        "soilName": soil.get("SOIL_NAME1"),
        "texture": decode_texture(soil.get("ATEXTURE1")),
        "textureGroup": texture_class["group"],
        "textureMudPotential": texture_class["mudPotential"],
        "drainage": drainage["label"],
        "drainageRank": drainage["rank"],
        "slopePercent": soil.get("SLOPE1"),
        "stoniness": decode_stoniness(soil.get("STONINESS1")),
        "parentMaterial": soil.get("PARNT_MAT1"),
    }


def enrich_description(trail_id):
    """Build one enriched trail-description record: the cleaned description
    plus terrain (bedrock/soil at the trail's lat/lng). Terrain is a
    property of the trail's location, not of any individual review, so it
    belongs here - fetched once per trail rather than once per review."""
    path = os.path.join(DATASETS_DIR, "cleaned_descriptions", f"{trail_id}.json")
    with open(path, "r", encoding="utf-8") as f:
        description = json.load(f)

    lat, lng = description["latitude"], description["longitude"]
    terrain = {
        "rock": _summarize_rock(fetch_rock_type(lat, lng)),
        "soil": _summarize_soil(fetch_soil_type(lat, lng)),
    }

    return {**description, "terrainData": terrain}


def save_enriched_description(trail_id, enriched_description):
    out_dir = os.path.join(DATASETS_DIR, "enriched_descriptions")
    os.makedirs(out_dir, exist_ok=True)
    out_path = os.path.join(out_dir, f"{trail_id}.json")
    with open(out_path, "w", encoding="utf-8") as f:
        json.dump(enriched_description, f, indent=2, ensure_ascii=False, default=str)
    print(f"saved enriched description to {out_path}")
    return out_path


# test: python -m scripts.enrich.enrich_description 10268327
if __name__ == "__main__":
    args = sys.argv[1:]
    if len(args) != 1:
        sys.exit(f"usage: python -m scripts.enrich.enrich_description <trail_id>\n\ngot {len(args)} argument(s): {args}")

    trail_id = args[0]
    if not trail_id.isdigit():
        sys.exit(f"trail_id must be numeric, got: {trail_id!r}")

    enriched = enrich_description(trail_id)
    save_enriched_description(trail_id, enriched)
