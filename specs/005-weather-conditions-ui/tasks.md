---

description: "Task list for Weather & Predicted Conditions UI"
---

# Tasks: Weather & Predicted Conditions UI

**Input**: Design documents from `specs/005-weather-conditions-ui/`

**Prerequisites**: plan.md, spec.md, research.md, data-model.md, contracts/conditions-api.md, quickstart.md

**Tests**: Backend tests included (matches this repo's existing convention — see `server/tests/test_weather.py`). No client test runner is configured in this repo; client verification is manual/browser-based per quickstart.md.

## Format: `[ID] [P?] [Story] Description`

## Phase 1: Setup

- [X] T001 Add `scikit-learn==1.6.1` and `joblib` to `server/requirements.txt`, install into `server/venv` (research.md decision 4 — 1.9.0 cannot unpickle the committed artifact)

**Checkpoint**: `server/venv/Scripts/python -c "import joblib; joblib.load('../data/datasets/models/condition_models.joblib')"` succeeds with no `AttributeError`.

---

## Phase 2: Foundational (blocking prerequisites for all user stories)

**Purpose**: The shared feature-flattening module and its consumers on both sides (Principle II), plus the schema/response-shape and weather-fetch plumbing every story's backend work depends on.

- [X] T002 Create `server/app/services/feature_flatten.py`: port `_flatten_weather`→`flatten_weather`, `_flatten_terrain`→`flatten_terrain`, `_flatten_description`→`flatten_description` (+ `DESCRIPTION_DROP_FIELDS`, `WEATHER_FIELDS`, `HISTORY_DAYS`) verbatim from `data/scripts/model/build_training_table.py`, and port `_antecedent_precip_index`→`antecedent_precip_index` (+ `ANTECEDENT_DAYS`, `ANTECEDENT_DECAY`) verbatim from `data/scripts/enrich/enrich_review.py`. Pure pandas/stdlib only — no FastAPI/pydantic imports (data/scripts must be able to import this without installing FastAPI).
- [X] T003 [P] In `data/scripts/model/build_training_table.py`: add a `sys.path` bootstrap to reach `server/` (`REPO_ROOT`-relative, next to the existing `DATASETS_DIR` computation), replace the local `_flatten_weather`/`_flatten_terrain`/`_flatten_description`/`DESCRIPTION_DROP_FIELDS`/`_WEATHER_FIELDS` definitions with imports from `app.services.feature_flatten`, keep `_add_multi_hot`/`_add_surface_percentages`/`build_training_table` unchanged. Verify with `python -m scripts.model.build_training_table <existing-trail-id>` from `data/` still reproduces the same columns.
- [X] T004 [P] In `data/scripts/enrich/enrich_review.py`: same `sys.path` bootstrap, replace the local `_antecedent_precip_index`/`ANTECEDENT_DAYS`/`ANTECEDENT_DECAY` with imports from `app.services.feature_flatten`. Verify `python -m scripts.enrich.enrich_data <trail_id> <review_id>` still produces the same `antecedentPrecipIndex` value as before.
- [X] T005 [P] Add `fetch_forecast_range(lat, lng, start_date, end_date)` to `server/app/services/open_meteo_client.py` (research.md decision 5) — same `_get`/`_zip_daily` building blocks `fetch_forecast` already uses, just `start_date`/`end_date` params instead of `forecast_days`.
- [X] T006 [P] In `server/app/schemas.py`: add `ConditionsConfidence` (`reviewCount: int`, `limitedData: bool`) and add `confidence: ConditionsConfidence` to `ConditionsResponse`.

**Checkpoint**: `feature_flatten.py` is importable from both `server/` (`from app.services.feature_flatten import ...`) and `data/scripts` (via the new bootstrap) with identical output on a known trail/review.

---

## Phase 3: User Story 1 - See predicted conditions for a chosen day (Priority: P1) 🎯 MVP

**Goal**: `GET /trails/{trail_id}/conditions` returns real model predictions; the Weather section renders raw weather + predictions + confidence + prep suggestions for the selected date, defaulting to today.

**Independent Test**: Open a trail's panel, scroll to Weather, see today's raw weather and predicted conditions render together (each condition with probability/flag/confidence), no full reload.

### Implementation for User Story 1

- [X] T007 [US1] Implement `server/app/services/conditions.py`: module-level lazy-loaded model bundle (`joblib.load(CONDITION_MODELS_PATH)`, cached after first call, `modelVersion` = artifact mtime as ISO date); date-range validation matching `weather.py`'s `[today, today+MAX_FORECAST_DAYS-1]` bound (422 `invalid_date_range` with `validRange`, reusing `WeatherErrorDetail`/`ValidRange`); trail lookup via `enriched_descriptions/{trail_id}.json` (404 `trail_unavailable` if missing or no lat/lng — mirrors `weather.py`'s `_get_trail_location` but returns the full parsed JSON, not just lat/lng); weather fetch via `fetch_forecast_range` over `[today-14, today+15]` cached per trail_id (30 min TTL, mirrors `weather.py`'s cache), sliced locally per requested date into the 15-record window `flatten_weather`/`antecedent_precip_index` need; upstream error classification (429→503 `upstream_rate_limited`, other→502 `upstream_unavailable`, mirrors `weather.py`'s `_classify_upstream_error`); feature-row assembly (`dayOfYear` inline, `flatten_weather`+`antecedent_precip_index`+`flatten_terrain`+`flatten_description` from the shared module, `feature_*`/`trail_surface_*_pct` computed against the model bundle's own fixed vocab, reindexed onto `model_bundle["features"]` exactly, `CATEGORICAL_COLUMNS = ["terrain_rockSlipRisk", "terrain_soilTextureGroup"]` cast to `category` dtype per research.md decision 3); per-condition `predict_proba`/threshold/flag, `condition_` prefix stripped for response keys, `dusty` naturally absent; confidence via `trail_activity.total_reviews` (reuse `get_trail_activity`, catching its 404 and treating it as `reviewCount=0`), `limitedData = reviewCount < 20`.
- [X] T008 [US1] `server/tests/test_conditions.py`: happy path (200, all 6 condition keys present with probability/predicted, confidence present, modelVersion present); `dusty` never in response; unenriched trail → 404 `trail_unavailable`; upstream 429 → 503, other upstream failure → 502 (monkeypatched `fetch_forecast_range`); zero-review trail → `limitedData: true`, `reviewCount: 0`, predictions still render (not blocked). Mirror `test_weather.py`'s fixture/monkeypatch style (`enriched_trail` fixture, `_clear_cache` autouse fixture for `conditions_module`'s cache).
- [X] T009 [P] [US1] In `client/src/api/trails.ts`: add `DailyWeather`, `WeatherWindow`, `ConditionResult`, `ConditionsResponse`, `ConditionsConfidence` types; add `getTrailWeatherWindow(trailId, startDate, endDate)` (calls `/weather?start_date&end_date`, returns `WeatherWindow | null` on 404) and `getTrailConditions(trailId, date)` (calls `/conditions?date`, returns `{ok: true, data} | {ok: false, errorType, message, validRange?}` — needs the error body, not just null-on-404, per FR-008/US3's distinct error messages).
- [X] T010 [US1] In `client/src/App.tsx`: extend `PanelState` with `selectedDate`, `weatherWindow: WeatherWindowState`, `conditionsByDate: Record<string, ConditionsDateState>` (data-model.md); on trail select, fetch the weather window once (`today`..`today+15`), default `selectedDate` to today once it resolves; add a `requestConditions(trailId, date)` helper that fetches-if-absent and writes into `conditionsByDate` keyed by date, guarding stale writes on `(trailId, date)` match (FR-020, same pattern as the existing `overview`/`popularity`/`route` guards); add `setSelectedDate(date)` that also triggers `requestConditions` for the newly-selected date if not already cached.
- [X] T011 [US1] Create `client/src/components/WeatherSection.tsx`: renders selected date's raw weather (temp high/low, precip, wind, snow) and predicted conditions side by side, each with its own loading skeleton (FR-013, matching `TrailOverview.tsx`/`PopularityChart.tsx`'s `Skeleton` convention); flagged conditions show the fixed prep-suggestion lookup (data-model.md); confidence line always rendered next to predictions (never a bare probability, SC-002); a prev/next day-stepper that calls `setSelectedDate` (bounded to the forecast window); distinct error messages for `trail_unavailable`/`upstream_rate_limited`/`upstream_unavailable`/`invalid_date_range` (US3, folded in here since the component owns conditions-error rendering). Use spec 004 tokens/skeleton/card conventions only — no new colors/radii.
- [X] T012 [US1] Mount `WeatherSection` in `client/src/App.tsx`'s `<TrailPanel>` children, after `TrailOverview`/`PopularityChart`, passing the relevant slice of `panel` state.

**Checkpoint**: User Story 1 fully functional and independently testable — `pytest server/tests/test_conditions.py` passes; opening a trail panel shows today's weather+predictions with confidence and prep suggestions; changing the day via the stepper updates both halves together.

---

## Phase 4: User Story 2 - Find the best day to go within the forecast window (Priority: P2)

**Goal**: A ~16-day strip colored by conditions favorability, with day-of-week popularity layered on, drives the same `selectedDate`.

**Independent Test**: Day Selection strip renders colored by favorability with popularity visible on the same strip; tapping a pill updates the Weather section above.

### Implementation for User Story 2

- [X] T013 [P] [US2] In `client/src/App.tsx`: on trail select (once `weatherWindow` resolves), kick off `requestConditions(trailId, date)` for all ~16 window dates in parallel (best-effort — one date's failure doesn't block the strip's other pills), per contracts/conditions-api.md.
- [X] T014 [US2] Create `client/src/components/DaySelectionSection.tsx`: horizontal strip of one pill per window date; each pill colored by that date's favorability (count of `predicted: true` conditions from `conditionsByDate`, data-model.md's derived ranking — no separate chart, FR-016/FR-017); day-of-week popularity (from `panel.popularity.data.byDayOfWeek`, already fetched for Overview) layered onto the same pill (e.g. a busy-ness dot/opacity), never rendered as its own chart (constitution Principle VI); tapping a pill calls `setSelectedDate`; the currently-selected date is visibly highlighted, matching whatever `selectedDate` is regardless of which surface set it (FR-015).
- [X] T015 [US2] Mount `DaySelectionSection` in `client/src/App.tsx`'s `<TrailPanel>` children, after `WeatherSection`.

**Checkpoint**: User Stories 1 AND 2 both work independently — picking a pill in Day Selection updates Weather above without losing scroll position; Weather section's own stepper keeps the strip's highlighted pill in sync.

---

## Phase 5: User Story 3 - Get a clear answer at the edges of what the app can predict (Priority: P3)

**Goal**: Out-of-horizon dates and pipeline/upstream failures produce specific, distinguishable messages, never a silent wrong guess.

**Independent Test**: Requesting conditions past the forecast horizon returns a specific "outside forecast range" message with the valid range, not a generic error or blank panel.

### Implementation for User Story 3

- [X] T016 [P] [US3] `server/tests/test_conditions.py` additions: date beyond horizon → 422 with `validRange.from`/`validRange.to` matching `weather.py`'s own bound exactly (same trail, same day, both endpoints agree); past date → 422.
- [X] T017 [US3] In `client/src/components/DaySelectionSection.tsx`: pills for dates beyond `weatherWindow`'s resolved range (or beyond `today+15` if the window itself came back short) render disabled/non-tappable, distinguishable from selectable pills (FR-018).
- [X] T018 [US3] Verify (extend if needed) `WeatherSection.tsx`'s error rendering from T011 covers all three distinct US3 messages: out-of-range date, trail not in pipeline, upstream unavailable/rate-limited — each visually distinct from the others and from the loading state.

**Checkpoint**: All three user stories independently functional; requesting an out-of-range date anywhere in the UI produces a specific, non-alarming, actionable message.

---

## Phase 6: Polish & Cross-Cutting Concerns

- [X] T019 [P] Run `pytest` in `server/` (full suite) — confirm no regressions in `test_weather.py`/`test_backfill.py`.
- [X] T020 [P] Run `tsc --noEmit` and `eslint` in `client/` on all changed/new files.
- [X] T021 Browser verification per `quickstart.md` steps 1-7 (default-today, flagged prep suggestions, confidence always visible, strip favorability+popularity layering, cross-surface sync, stale-response guard via rapid pill taps, disabled out-of-horizon pills) using the preview tools; capture a screenshot.
- [X] T022 [P] Update `server/README.md`'s Status section: move `/trails/{trail_id}/conditions` out of "stubbed" into the working-endpoints list, same style as the existing `/weather` entry.

---

## Dependencies & Execution Order

- **Setup (T001)** — no dependencies.
- **Foundational (T002-T006)** — depends on T001 (needs a working sklearn/joblib env to validate T002 against the real artifact); BLOCKS all user stories. T003/T004/T005/T006 are independent of each other (different files) once T002 exists.
- **User Story 1 (T007-T012)** — depends on Foundational. T007 depends on T002/T005/T006. T008 depends on T007. T009 is independent (client-only). T010 depends on T009. T011 depends on T009/T010. T012 depends on T011.
- **User Story 2 (T013-T015)** — depends on Foundational + US1's T009/T010 (reuses `requestConditions`/`PanelState`) and T011 (Weather section must exist for "updates the section above" to be checkable), but is its own independently-deliverable increment on top.
- **User Story 3 (T016-T018)** — depends on US1's T007 (backend validation already exists) and US2's T014 (strip to disable pills on); mostly verification + the disabled-pill visual state.
- **Polish (T019-T022)** — after all desired stories are complete.

### Parallel Opportunities

- T003, T004, T005, T006 in parallel once T002 lands.
- T009 can start in parallel with T007/T008 (client types don't need the backend running).
- T013 and T016 can run in parallel with each other (different concerns, no shared file).
- T019, T020, T022 in parallel at the end.

## Implementation Strategy

**MVP = User Story 1** (T001-T012): a working `/conditions` endpoint and a Weather section that shows today's predictions with confidence, independent of the day-strip. Stop and validate here before adding US2's strip.

**Incremental delivery**: Setup+Foundational → US1 (MVP, demoable) → US2 (adds trip-planning value) → US3 (hardens the edges) → Polish.
