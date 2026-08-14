import re

# Ontario's provincial bedrock layer (GeologyOntario_Map/57) only has 111
# distinct ROCKTYPE_P lithology descriptions across the whole province (see
# LABEL_CONDITIONS.md-style research note: queried via returnDistinctValues,
# not sampled) - free text like "Limestone, dolostone, shale" or "Granite,
# alkali granite, granodiorite", often listing several rock types per unit.
# Too high-cardinality/one-off to use as a categorical feature directly, and
# there's no ArcGIS coded domain to decode it against - so this is a
# hardcoded keyword -> category mapping, built from that actual vocabulary,
# the same pattern as the keyword-based condition labeling in
# ../label/label_conditions_keyword.py.
#
# `slip_risk` reflects wet-rock traction underfoot, which is the hiking-
# relevant angle for a trail-conditions model, not standard petrology
# groupings (that's why marble - a metamorphic carbonate - sits with
# limestone/dolostone rather than with granite/gneiss):
#   - "low": rough/crystalline/coarse-grained, keeps grip wet or dry
#     (granite, sandstone, gabbro, quartzite)
#   - "moderate": foliated or fine-grained rock, can get slick along
#     grain/foliation planes when wet or mossy (gneiss, schist, volcanics)
#   - "high": rock types hikers and land managers specifically flag as
#     slippery when wet - polished carbonates (limestone, dolostone,
#     marble) and fissile fine clastics (shale, slate, argillite)
ROCK_CATEGORIES = {
    "granitic_intrusive": {
        "keywords": [
            "granite", "granodiorite", "tonalite", "monzogranite", "syenogranite",
            "monzonite", "syenite", "granophyre", "pegmatite", "monzondiorite",
        ],
        "slip_risk": "low",
    },
    "mafic_intrusive": {
        "keywords": [
            "gabbro", "diorite", "anorthosite", "norite", "peridotite",
            "pyroxenite", "dike", "dikes", "sill", "sills",
        ],
        "slip_risk": "low",
    },
    "ultramafic": {
        "keywords": ["ultramafic", "komatiite", "komatiitic"],
        "slip_risk": "low",
    },
    "quartzite": {
        "keywords": ["quartzite"],
        "slip_risk": "low",
    },
    "coarse_clastic_sedimentary": {
        "keywords": [
            "sandstone", "conglomerate", "arenite", "arkose", "wacke",
        ],
        "slip_risk": "low",
    },
    "gneiss_migmatite": {
        "keywords": [
            "gneiss", "gneisses", "gneissic", "migmatite", "migmatites",
            "migmatitic", "paragneiss", "orthogneiss", "mylonite", "mylonites",
            "tectonite", "tectonites",
        ],
        "slip_risk": "moderate",
    },
    "schist": {
        "keywords": ["schist"],
        "slip_risk": "moderate",
    },
    "volcanic": {
        "keywords": [
            "basalt", "basaltic", "rhyolite", "rhyolitic", "rhyodacitic",
            "andesite", "andesitic", "dacite", "dacitic", "tuff", "tuffs",
            "breccia", "breccias", "volcanic", "metavolcanic", "pyroclastic",
        ],
        "slip_risk": "moderate",
    },
    "alkalic_carbonatite": {
        "keywords": ["carbonatite", "fenite", "ijolite", "nepheline"],
        "slip_risk": "moderate",
    },
    "carbonate_sedimentary": {
        "keywords": ["limestone", "dolostone", "dolomite"],
        "slip_risk": "high",
    },
    "marble": {
        "keywords": ["marble"],
        "slip_risk": "high",
    },
    "fine_clastic_sedimentary": {
        "keywords": [
            "shale", "argillite", "siltstone", "mudstone", "slate", "taconite",
        ],
        "slip_risk": "high",
    },
}

_RISK_RANK = {"low": 0, "moderate": 1, "high": 2}

_CATEGORY_PATTERNS = {
    category: re.compile(
        r"\b(" + "|".join(re.escape(kw) for kw in spec["keywords"]) + r")\b",
        re.IGNORECASE,
    )
    for category, spec in ROCK_CATEGORIES.items()
}


def classify_rock(rocktype_text):
    """Match a raw ROCKTYPE_P description against every category's
    keywords (a unit description often lists several rock types, e.g.
    "Limestone, dolostone, shale, sandstone" -> carbonate_sedimentary +
    fine_clastic_sedimentary + coarse_clastic_sedimentary) and return:
    - categories: every matched category, for multi-hot use downstream
    - slipRisk: the *worst* (most slippery-when-wet) risk among matches -
      a single cautious scalar, since a trail through mixed lithology is
      only as good as its worst footing.
    None fields when the text is empty or matches nothing known."""
    if not rocktype_text or not rocktype_text.strip():
        return {"categories": [], "slipRisk": None}

    categories = [
        category
        for category, pattern in _CATEGORY_PATTERNS.items()
        if pattern.search(rocktype_text)
    ]
    if not categories:
        return {"categories": [], "slipRisk": None}

    worst_risk = max(categories, key=lambda c: _RISK_RANK[ROCK_CATEGORIES[c]["slip_risk"]])
    return {
        "categories": sorted(categories),
        "slipRisk": ROCK_CATEGORIES[worst_risk]["slip_risk"],
    }
