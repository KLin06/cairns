---
name: add-enrichment-field
description: After a new field has been added to the trail-conditions enrichment pipeline (data/scripts/), detect which stage it touched and rerun only what that invalidates - not the whole pipeline. Use when the user says they just added/changed an enrichment field, terrain attribute, weather signal, or review-derived label and wants the pipeline caught up.
---

# Rerun the enrichment pipeline after a field change

This repo's pipeline is: `scrape` -> `clean` -> `enrich` (per-trail
description + per-review data) -> `build_training_table.py` ->
`train_model.py`. Re-running the whole thing from `enrich` is 100x more
expensive (real Open-Meteo/AllTrails calls per trail) than it needs to be
for most field additions. Figure out what actually changed before running
anything.

## Step 1 - find what changed

Run `git diff` (or `git diff --staged` if the change is staged) scoped to
`data/scripts/` and read it. Classify based on which files it touches:

- Touches only
  [build_training_table.py](../../../data/scripts/model/build_training_table.py)
  (a new column derived inside `_flatten_description`/`_flatten_terrain`/
  `_flatten_review` from fields already present in
  `enriched_reviews/*.json` / `enriched_descriptions/*.json`) -> **derived-only**.
- Touches
  [enrich_description.py](../../../data/scripts/enrich/enrich_description.py)
  (or a new client it calls, e.g. under `data/scripts/enrich/terrain/`) ->
  **trail-level**.
- Touches
  [enrich_review.py](../../../data/scripts/enrich/enrich_review.py)'s
  `enrich_data` (or something it calls) -> **review-level**.
- Touches both an enrich file and `build_training_table.py` -> use the
  enrich-side classification (trail-level or review-level wins; that's the
  expensive part).

If the diff is ambiguous or you can't tell whether the new logic reads only
already-saved fields vs. needs a fresh fetch, ask the user rather than
guessing - the cost difference between the branches below is large.

Also check whether the new/changed field is a plain string meant to be used
natively by `HistGradientBoostingClassifier` - if so, confirm it's been
added to `CATEGORICAL_COLUMNS` in
[train_model.py](../../../data/scripts/model/train_model.py) (cast to
pandas `category` dtype in `load_training_table`); flag it if not, since a
raw object-dtype column will break training rather than degrade silently.

## Step 2 - rerun accordingly

**Derived-only:** nothing upstream needs to re-run.
```bash
python -m scripts.model.build_training_table
python -m scripts.model.train_model
```

**Trail-level:** do **not** run the full `enrich` stage via
`python -m scripts.trails enrich` - that also walks every review through
`enrich_data`, wasted work (and wasted API calls) for a field that only
touches descriptions. Re-run just the description half, once per trail
already in `enriched_descriptions/`:

```python
# from data/, inside the venv
import os, glob
from scripts.paths import DATASETS_DIR
from scripts.enrich.enrich_description import enrich_description, save_enriched_description

trail_ids = [
    os.path.splitext(os.path.basename(p))[0]
    for p in glob.glob(os.path.join(DATASETS_DIR, "enriched_descriptions", "*.json"))
]
for trail_id in trail_ids:
    save_enriched_description(trail_id, enrich_description(trail_id))
```
Then rebuild the table and retrain (same two commands as above).

**Review-level - the trap to watch for:** `enrich_trail`'s resume logic
(`_load_existing_enriched` in `enrich_trail.py`) treats any `reviewId`
already present in `enriched_reviews/{trail_id}.json` as done and never
re-enriches it. That means **just re-running
`python -m scripts.trails enrich` (even with `--retry-failed`) will NOT
backfill the new field into reviews that were already enriched** - it only
picks up brand-new reviews. Two real options, pick based on cost:

1. **Full recompute (correct but expensive)** - delete the affected trails'
   entries from `enriched_reviews/` (and clear their `"enrich"` status in
   `data/datasets/explore/pipeline_state.json`) and re-run
   `python -m scripts.trails enrich`. This redoes every review's weather
   window and labeling, not just the new field. Only worth it if the new
   field's logic needs a genuinely fresh fetch (e.g. a new external call
   per review).

2. **Targeted backfill (cheap, preferred when the new field is derived from
   data already saved on a review, e.g. re-derived from `historicalWeather`
   or review text)** - write a small script that loads each trail's
   existing `enriched_reviews/{trail_id}.json`, computes just the new field
   per record (reusing the relevant helper, not the whole `enrich_data`
   function), adds it, and re-saves via `save_enriched_trail`. No
   weather/AllTrails calls at all.

Ask the user which applies before choosing - option 1 makes real network
calls across every trail in the explore index, which is exactly the kind of
bulk/external-facing action to confirm before running, not assume.

After either path, rebuild and retrain:
```bash
python -m scripts.model.build_training_table
python -m scripts.model.train_model
```

## Step 3 - sanity check

- Confirm the new column shows up in `data/datasets/training_table/reviews.csv`.
- If it's categorical, confirm `train_model.py` didn't drop it in
  `_drop_zero_variance` (expected/harmless on a small trail sample per that
  function's own docstring, but worth noting to the user if it happens).
- If this pipeline feeds `server/app/`'s live inference path (see
  [APP_SPEC.md](../../../APP_SPEC.md)'s "Feature reconstruction at inference
  time" section), flag that the backend's feature-assembly function needs
  the same new field added in the same shape, or inference will break on
  the next retrain.
