# Trail Conditions Model — Notes & Improvement Log

Companion to `TRAIL_CONDITIONS_PLAN.md` (the original design doc, focused on
data/labeling) and `enrich/label/LABEL_CONDITIONS.md` (the condition labeler
itself) — this one tracks the model in `train_model.py` specifically: what's
been tried, why, what it measurably changed, and what's still worth doing.

## Current setup

- **One binary `HistGradientBoostingClassifier` per condition**
  (`bugs`, `flooded`, `icy`, `muddy`, `slippery`, `snow`), not one shared
  multi-label model — a review can be muddy *and* icy *and* buggy at once,
  and each condition plausibly depends on a different subset of features
  (mud on soil drainage, ice on temperature), so independent models let
  each one learn its own decision boundary instead of compromising.
- **Split by trail (`GroupShuffleSplit`), three-way**: fit (train) / val
  (pick each condition's probability threshold) / test (final, only
  looked at once). Never a random row split once ≥2 trails exist — reviews
  on the same trail share near-identical weather/terrain, so a random
  split leaks near-duplicates between train and test and overstates
  generalization to a trail the model hasn't seen.
- **Features**: 8-day weather window (`weather_d0_*` = hike day through
  `weather_d7_*` = a week before, each with tempMax/tempMin/rain/snow/
  windMax), `dayOfYear`, trail terrain (`terrain_rockSlipRisk`,
  `terrain_soilDrainageRank`, `terrain_soilTextureMudPotential`,
  `terrain_soilTextureGroup`), `trail_length`, `trail_difficultyRating`,
  surface-type percentages. See `build_training_table.py` for the full
  flatten/join logic.
- **Targets**: `condition_*` columns, derived from AllTrails'
  obstacles/trailConditions tags + our own keyword/embedding text labeler,
  merged and canonicalized (see `CONDITION_CATEGORY_MAP` in
  `enrich_review.py`).

## Improvement log

Roughly chronological. Each entry is something that measurably changed
either the data volume/quality feeding the model, or the model's own
training/evaluation setup.

### Data pipeline fixes (more/better training data)

- **Fixed the `comment_lang == "en-US"` filter dropping ~74% of reviews
  for the wrong reason.** Most reviews with a blank `comment_lang` had no
  comment at all (nothing to language-detect) or were genuinely English
  text AllTrails just never ran detection on — not foreign language. New
  filter keeps everything except reviews explicitly tagged as a
  *non*-English language. One trail's cleaned reviews went from 975 to
  4,311 as a direct result.
- **Removed the `activity.isin(["Hiking", "Backpacking"])` filter.**
  Mud/ice/snow are physical trail properties, not activity-dependent — a
  snowshoer or mountain biker reporting "muddy" is still valid signal.
  This filter was only cutting ~4% of reviews, but for no real reason.
- **Fixed a crash on reviews with no comment text.** `comment or ""` in
  the labeler doesn't catch `NaN` (a float, and truthy in Python) the way
  it catches `None`/empty string — every review recovered by the
  `comment_lang` fix that also happened to have zero comment text was
  crashing the labeler. Fixed by checking `isinstance(comment, str)`
  explicitly instead of relying on truthiness.
- **Terrain data (bedrock/soil) moved from a review-level lookup to a
  trail-level one** (`enrich_description.py`), and expanded from raw
  ArcGIS attribute dumps into curated, hiking-relevant fields: rock
  lithology → wet-traction category (`rock_classification.py`, keyword
  matching against Ontario's ~111 distinct bedrock unit descriptions) and
  soil texture → mud-potential score (`soil_codes.py`, decoding the
  standard Canadian soil-survey texture/drainage codes). These are the
  features specifically meant to give `muddy`/`slippery` predictive power
  beyond "it rained."
- **Added `dayOfYear`** to every enriched review — seasonality (spring
  thaw, first snow) that raw weather alone doesn't fully capture.
- **Condition labels canonicalized and pruned**
  (`CONDITION_CATEGORY_MAP`). AllTrails' own obstacle/condition tags cover
  more than physical conditions (`Fee`, `Great!`, `Well maintained` are
  about cost/experience) and spell the same condition differently
  depending on source (`Buggy` vs `Bugs`, `Snow` vs our labeler's
  `snowy`). Trimmed down to a fixed set the model actually trains on:
  `bugs`, `dusty`, `flooded`, `muddy`, `icy`, `slippery`, `snow` (later:
  see "dusty excluded" below). `rock`/`scramble` were tried and then
  dropped entirely — not model-relevant conditions, more like trail
  terrain/difficulty descriptors.

### Feature engineering

- **Weather kept per-day, not aggregated.** Originally collapsed the
  8-day window into one weekly aggregate (mean temp, total precip);
  switched to `weather_d0_*` … `weather_d7_*` as separate columns, since
  "rained yesterday" and "rained a week ago" have very different
  implications for mud and a single average erases that distinction.
- **Dropped `precipitation_sum` as a feature.** Verified against real
  data: every case where `precip != rain` lined up exactly with a nonzero
  `snow` value (0 unexplained mismatches out of 9,384 day-records) —
  `precip` is just `rain + snow`'s water equivalent, pure redundant
  information given both components are already separate columns.
- **Bulk weather fetching instead of per-review calls.** Originally one
  Open-Meteo call per review (~thousands per trail); switched to fetching
  a trail's *entire* review-date range in 1-2 calls
  (`fetch_full_history`/`preload_trail_weather`) and slicing each
  review's window out locally. Doesn't change model quality, but was
  necessary to stay within Open-Meteo's free-tier daily quota once
  scraping scaled past a handful of trails.
- **Dropped low/no-signal columns from the training table**:
  `trail_ratingValue`, `trail_reviewCount`, `trail_popularity`,
  `trail_areaName`, `trail_addressLocality`, `activity`, `rating` (review
  star rating) — all either identifiers, popularity metrics several
  inferential steps removed from physical trail conditions, or redundant
  once terrain/weather features exist.

### Model training

- **`class_weight="balanced"`.** Several conditions have low positive
  rates (`bugs`/`icy` ~8%, `flooded` ~7.5%); without reweighting, the
  loss is minimized by defaulting to "False" almost everywhere. This
  roughly tripled recall on the positive class across every condition
  (e.g. `slippery` 0.16 → 0.74, `icy` 0.12 → 0.59) at some cost to
  ROC-AUC on a couple of conditions (`icy` 0.844 → 0.826, `snow` 0.847 →
  0.786) — a deliberate trade, not a regression.
- **Per-condition probability threshold, tuned on a held-out validation
  split** (`_best_threshold`, maximizes F1 on the precision-recall
  curve), instead of a blanket 0.5 for every condition. Picked from
  `val`, evaluated on `test` — picking the threshold from the same data
  used to report metrics would make the numbers optimistic. Thresholds
  are saved alongside the models in `condition_models.joblib` and read at
  inference time.
- **`dusty` excluded from training entirely**
  (`EXCLUDED_CONDITIONS`). Only 21 positive examples out of 21,433 rows
  (0.1%) — not enough to learn from or evaluate; its ROC-AUC came out at
  0.298 (worse than random), which is noise from a handful of test-set
  positives landing unluckily, not a real signal that the model learned
  something backwards.
- **Zero-variance feature filtering** (`_drop_zero_variance`) — a
  defensive fix, not a quality improvement: `HistGradientBoostingClassifier`
  crashes outright on an all-NaN/all-constant column rather than ignoring
  it, which happened constantly while the training table only spanned one
  trail (terrain/lat-lng features were all identical). Necessary for the
  code to run at all with partial data; drops should stop happening
  naturally as more trails are enriched.

## Recommended next improvements (not yet done)

Roughly in order of effort-to-impact:

- [ ] **Add elevation / elevation-gain as a feature.** The original
  problem statement calls out "ice on switchbacks at elevation" as a
  concrete failure mode of static difficulty ratings — there's currently
  no elevation feature at all (`trail_length` exists, elevation profile
  doesn't). AllTrails' own data may have this (`elevationGainFt` was
  mentioned as available in `TRAIL_CONDITIONS_PLAN.md`'s original data
  survey, worth confirming it's still exposed and wiring it through
  clean/enrich/build_training_table).
- [ ] **Add a distance-to-water feature for `flooded`.** Currently only a
  boolean `feature_Lakes` tag; `flooded` is the weakest-performing
  condition (ROC-AUC ~0.6) and a continuous proximity-to-water-body
  feature is a more direct plausible cause than a yes/no amenity tag.
- [ ] **Hyperparameter search, grouped by trail.** Every model is
  currently trained on `HistGradientBoostingClassifier` defaults
  (`max_iter=100`, `learning_rate=0.1`, no tuning at all). A modest grid/
  random search over `max_iter`/`learning_rate`/`min_samples_leaf` with
  `GroupKFold` (by `trailId`, same reasoning as the train/test split) is
  untapped.
- [ ] **Validate/retune the text labeler's margin threshold with more
  manual-labeled data.** Condition labels come from an embedding-based
  labeler validated against only 145 manually-labeled reviews
  (`manual_labels/10268327.json`, see `LABEL_CONDITIONS.md`). Label noise
  caps model performance regardless of feature/model quality — worth
  expanding that validation set now that there's far more data to sample
  borderline cases from.
- [ ] **Calibrate probabilities** (`CalibratedClassifierCV`) before
  showing them to users. `predict_proba` from a raw
  `HistGradientBoostingClassifier` isn't guaranteed well-calibrated, and
  the app plans to show the raw probability directly (e.g. "62% chance of
  mud"), not just a threshold-bucketed label — calibration matters a lot
  for a number a user reads literally, less for ranking/AUC.
- [ ] **Revisit `dusty`** once enough trails/reviews have accumulated
  that it has a meaningful number of positive examples.
