# Phase 0 Research

## Decision 1: Shared flatten module lives in `server/`, `data/scripts` imports it (not the reverse)

**Decision**: Create `server/app/services/feature_flatten.py` containing the row-level flatten
functions (`flatten_weather`, `antecedent_precip_index`, `flatten_terrain`, `flatten_description`
+ their constants). `data/scripts/model/build_training_table.py` and
`data/scripts/enrich/enrich_review.py` import from it (via a small `sys.path` bootstrap to reach
`server/`), replacing their own local `_flatten_weather`/`_flatten_terrain`/`_flatten_description`/
`_antecedent_precip_index` definitions.

**Rationale**: `server/app/config.py` already states the design rule explicitly: "server/ ... 
doesn't import any data/scripts Python code either - server/ is meant to run standalone with its
own requirements.txt." That constraint is one-directional. `data/scripts` is offline dev/pipeline
tooling with a much heavier dependency footprint already (torch, transformers, sentence-transformers)
and no standalone-deployment requirement, so it can safely depend on `server/`. This satisfies
constitution Principle II ("single shared implementation... MUST NOT be reimplemented separately")
without weakening server's standalone-deployment property.

**Alternatives considered**:
- A third top-level `shared/` package: rejected — would make *both* sides depend on a new
  directory, which is a bigger structural change than necessary and still has to be bundled with
  server's deployment, contradicting "server run standalone."
- Reimplement independently in `conditions.py` per the stub's literal TODO wording: rejected — this
  is exactly the drift risk Principle II exists to prevent; the whole reason to write this plan
  step is to avoid it.

## Decision 2: Live inference reads `enriched_descriptions/{trail_id}.json` directly, not the `trails` Postgres table

**Decision**: `conditions.py` loads the trail's raw enriched-description JSON (same file
`weather.py`'s `_get_trail_location` already reads) rather than querying the `trails` table like
`trail_info.py` does.

**Rationale**: The trained model's feature list includes `terrain_soilDrainageRank`,
`terrain_soilTextureMudPotential`, and `terrain_soilTextureGroup` (confirmed by loading
`condition_models.joblib` directly — see below). The `trails` table (`specs/002-trail-data-storage-schema`)
only persists `rock_slip_risk` and `soil_drainage` (a human-readable label), per constitution
Principle IX (selective storage — only what something already consumes). Adding three ML-only
columns to Postgres for a single new consumer would be schema churn for fields nothing else reads,
and a DB migration is explicitly out of this feature's scope. Reading the same JSON file
`build_training_table.py` reads keeps Feature Parity exact by construction — it's the same
`terrainData` shape flowing through the same `flatten_terrain`.

**Alternatives considered**: Add the three fields to the `trails` table via a new migration —
rejected, contradicts Principle IX (nothing besides the ML feature vector would consume them) and
adds unnecessary scope.

## Decision 3: Ground-truth feature list confirmed by loading the artifact directly

Loaded `condition_models.joblib` (after resolving the sklearn version issue below) and inspected it
directly rather than inferring the feature list purely from reading `build_training_table.py`:

```
CONDITIONS: bugs, flooded, icy, muddy, slippery, snow (dusty absent, as expected)
N FEATURES: 70
```

Full list: `dayOfYear`, `antecedentPrecipIndex`, `weather_d0_*`..`weather_d7_*` (5 fields × 8 days =
40), `trail_latitude`, `trail_longitude`, `trail_length`, `trail_difficultyRating`,
`terrain_rockSlipRisk`, `terrain_soilDrainageRank`, `terrain_soilTextureMudPotential`,
`terrain_soilTextureGroup`, 11 `feature_*` columns (fixed vocabulary baked in at training time:
Caves, Dogs_on_leash, Fee_required, Forests, Kid-friendly, Lakes, Partially_paved, Rivers, Rocky,
Stroller-friendly, Wildlife), 9 `trail_surface_*_pct` columns (grass, gravel, metal, natural,
paved, sand, steps, unknown, wood).

**Implication for inference**: since the `feature_*`/`trail_surface_*_pct` vocabulary is fixed
(baked into `model_bundle["features"]`, not rediscovered), live inference doesn't need
`build_training_table.py`'s batch vocabulary-discovery step (`_add_multi_hot`/
`_add_surface_percentages`, which scans an entire training dataframe) — it just needs to test, for
each of those known column names, whether *this* trail's own feature/surface list contains a
matching entry, then reindex the assembled row onto `model_bundle["features"]` exactly. Any column
absent from a trail's own data naturally reindexes to `False`/`0`/`NaN`, matching training-time
defaulting.

**Implication for categorical dtype**: `train_model.py`'s `CATEGORICAL_COLUMNS =
["terrain_rockSlipRisk", "terrain_soilTextureGroup"]` is a training-config fact, not flattening
logic — it's a two-string constant, not worth pulling `train_model.py` (and its sklearn training
imports) into the shared module. Duplicated as a local constant in `conditions.py` with a comment
pointing at the source of truth, same pattern already used for `MAX_RETRIES`/`RETRY_BASE_DELAY`
duplication between `server/app/services/open_meteo_client.py` and
`data/scripts/enrich/weather/open_meteo.py`.

## Decision 4: scikit-learn version pin

**Finding**: `data/venv` currently has `scikit-learn==1.9.0`. Attempting to `joblib.load()` the
committed `condition_models.joblib` under 1.9.0 fails:
`AttributeError: Can't get attribute '_RemainderColsList' on <module 'sklearn.compose._column_transformer'>`
— the artifact was pickled under an older sklearn (`InconsistentVersionWarning` names 1.6.1) whose
internal `HistGradientBoostingClassifier(categorical_features="from_dtype")` preprocessing objects
aren't forward-compatible with 1.9.0's refactored `ColumnTransformer` internals.

**Decision**: Pin `scikit-learn==1.6.1` (+ `joblib`) in `server/requirements.txt`. Verified this
version successfully unpickles the artifact and exposes `models`/`features`/`thresholds` as
documented.

**Alternatives considered**: Retrain the model under 1.9.0 — explicitly out of scope per the
spec's Assumptions ("no retraining ... in scope"). Fixing `data/venv`'s sklearn version is a
separate, pre-existing environment inconsistency outside this feature's scope (data/venv isn't
touched by this feature at all); flagged for a follow-up, not fixed here.

## Decision 5: One wide weather fetch per trail instead of one `fetch_forecast_with_history` call per date

**Decision**: Instead of literally porting `fetch_forecast_with_history(lat, lng, date,
history_days)` (one Open-Meteo call per target date), add
`fetch_forecast_range(lat, lng, start_date, end_date)` to `server/app/services/open_meteo_client.py`
and call it once per trail with `start_date = today - 14`, `end_date = today + 15` (the widest
window any valid request date could need — the Day Selection strip needs conditions for all ~16
forecast-window days, and the Weather section needs the 7-day-lookback + 14-day-antecedent window
behind whichever single day is selected). Cache the whole window per trail_id (30-minute TTL,
mirroring `weather.py`'s existing cache), then slice the needed sub-window out locally per
requested date.

**Rationale**: The Day Selection strip (FR-016) needs a favorability ranking for every day in the
window, which means the backend gets a conditions request per date shown on the strip. Fetching a
fresh Open-Meteo window per date (16 near-duplicate calls covering overlapping ranges) would be
wasteful and risk the exact rate-limiting `weather.py` already guards against. Open-Meteo's daily
forecast endpoint accepts `start_date`/`end_date` directly (the same underlying mechanism
`fetch_forecast_with_history` already relies on for its own recent-past window), so one call with
a wide-enough range serves every date in the valid request range.

**Alternatives considered**: Literal port of `fetch_forecast_with_history`, called once per
requested date — rejected per above (avoidable N-times upstream traffic for the strip's 16 dates).
