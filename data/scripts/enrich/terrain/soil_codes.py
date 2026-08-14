# The LIO soil survey layer (LIO_OPEN_DATA/LIO_Open05/9) doesn't expose
# ArcGIS coded-value domains for these fields (checked via the layer's own
# ?f=json metadata - no `domain` on any field), but querying
# returnDistinctValues shows they're short, closed code sets (standard
# Canadian soil-survey abbreviations), not free text - so this is a fixed
# lookup table, not a keyword classifier like rock_classification.py.

# ATEXTURE1: dominant soil texture class. Coarser/sandier textures drain
# fast and resist mud; finer clay-heavy textures hold water and are the
# ones that turn a trail to mud after rain.
TEXTURE_LABELS = {
    "C": "clay",
    "CL": "clay loam",
    "CSL": "coarse sandy loam",
    "FS": "fine sand",
    "FSL": "fine sandy loam",
    "GL": "gravelly loam",
    "GLS": "gravelly loamy sand",
    "GRAV": "gravel",
    "GS": "gravelly sand",
    "GSL": "gravelly sandy loam",
    "L": "loam",
    "LCS": "loamy coarse sand",
    "LFS": "loamy fine sand",
    "LS": "loamy sand",
    "LVFS": "loamy very fine sand",
    "ORG": "organic",
    "R": "rockland",
    "S": "sand",
    "SCL": "sandy clay loam",
    "SIC": "silty clay",
    "SICL": "silty clay loam",
    "SIL": "silt loam",
    "SL": "sandy loam",
    "VFS": "very fine sand",
    "VFSL": "very fine sandy loam",
    "VA": "variable",
    "VAR": "variable",
    "WA": "water",
    "NA": None,
}

# DRAINAGE1: how readily water moves through/off the soil - the single
# most directly relevant soil field for a trail-conditions model, since
# poor drainage is close to a direct proxy for "goes to mud after rain".
# `rank` is ordinal, 0 (best drained, least mud-prone) to 6 (worst
# drained, most mud-prone) - a value linear/distance models can use
# directly, unlike the bare code.
DRAINAGE_LABELS = {
    "VR": {"label": "very rapid", "rank": 0},
    "R": {"label": "rapid", "rank": 1},
    "W": {"label": "well", "rank": 2},
    "MW": {"label": "moderately well", "rank": 3},
    "I": {"label": "imperfect", "rank": 4},
    "P": {"label": "poor", "rank": 5},
    "VP": {"label": "very poor", "rank": 6},
    "WA": {"label": "water", "rank": None},
    "VA": {"label": "variable", "rank": None},
    "NA": {"label": None, "rank": None},
}


# TEXTURE_LABELS's 29 codes are too fine-grained to be a useful model
# feature on their own (many trails will never see most of them) - grouped
# here into the broad classes that actually govern "does this turn to mud":
#   - "clay": high water-holding fine particles, the classic mud texture
#   - "silt": small particles like clay but different structure - silty
#     ground is well known among hikers for going slick/muddy when wet,
#     so grouped separately from loam rather than folded into it
#   - "loam": balanced mix, moderate mud potential
#   - "sand": coarse, drains fast, resists mud
#   - "organic": peat/muck - saturated wetland/bog soils, usually the
#     muddiest ground there is despite not being "clay"
#   - "rock": bedrock outcrop, effectively no soil to hold water as mud
# `mudPotential`: 0 (low) - 2 (high), the actual "is this muddy" signal.
TEXTURE_CLASSIFICATION = {
    "C": {"group": "clay", "mudPotential": 2},
    "SIC": {"group": "silt", "mudPotential": 2},
    "SICL": {"group": "silt", "mudPotential": 2},
    "SIL": {"group": "silt", "mudPotential": 2},
    "CL": {"group": "clay", "mudPotential": 2},
    "SCL": {"group": "clay", "mudPotential": 1},
    "ORG": {"group": "organic", "mudPotential": 2},
    "L": {"group": "loam", "mudPotential": 1},
    "GL": {"group": "loam", "mudPotential": 1},
    "SL": {"group": "loam", "mudPotential": 1},
    "FSL": {"group": "loam", "mudPotential": 1},
    "VFSL": {"group": "loam", "mudPotential": 1},
    "CSL": {"group": "loam", "mudPotential": 0},
    "GSL": {"group": "loam", "mudPotential": 0},
    "S": {"group": "sand", "mudPotential": 0},
    "FS": {"group": "sand", "mudPotential": 0},
    "VFS": {"group": "sand", "mudPotential": 0},
    "LS": {"group": "sand", "mudPotential": 0},
    "LFS": {"group": "sand", "mudPotential": 0},
    "LVFS": {"group": "sand", "mudPotential": 0},
    "LCS": {"group": "sand", "mudPotential": 0},
    "GRAV": {"group": "sand", "mudPotential": 0},
    "GS": {"group": "sand", "mudPotential": 0},
    "GLS": {"group": "sand", "mudPotential": 0},
    "R": {"group": "rock", "mudPotential": 0},
    "WA": {"group": None, "mudPotential": None},
    "NA": {"group": None, "mudPotential": None},
    "VA": {"group": None, "mudPotential": None},
    "VAR": {"group": None, "mudPotential": None},
}


def decode_texture(code):
    if not code:
        return None
    return TEXTURE_LABELS.get(code, code)


def classify_texture(code):
    """Returns {"group": str | None, "mudPotential": int | None} - see
    TEXTURE_CLASSIFICATION above."""
    if not code:
        return {"group": None, "mudPotential": None}
    return TEXTURE_CLASSIFICATION.get(code, {"group": None, "mudPotential": None})


def decode_drainage(code):
    """Returns {"label": str | None, "rank": int | None}."""
    if not code:
        return {"label": None, "rank": None}
    return DRAINAGE_LABELS.get(code, {"label": code, "rank": None})


def decode_stoniness(code):
    """STONINESS1 is already an ordinal 0 (no stones) - 9 (extremely
    stony/exposed rock) scale, with "N" meaning no data - just needs
    casting to int, no lookup table."""
    if not code or code == "N":
        return None
    try:
        return int(code)
    except ValueError:
        return None
