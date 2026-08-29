# Implementation Plan: Weather & Predicted Conditions UI

**Branch**: `005-weather-conditions-ui` | **Date**: 2026-08-29 | **Spec**: [spec.md](./spec.md)

**Input**: Feature specification from `/specs/005-weather-conditions-ui/spec.md`

## Summary

Implement the model-backed `GET /trails/{trail_id}/conditions` endpoint (currently a 501 stub)
and the trail panel's Weather + Day Selection sections. Backend: factor the row-flattening logic
`build_training_table.py` uses into a shared module under `server/app/services/`, port a
forecast-window weather fetch into `server/`, load `condition_models.joblib` once, and run
per-condition inference with per-condition tuned thresholds. Frontend: add two new panel sections
sharing one `selectedDate` piece of state with a 16-day day-strip that doubles as both the date
picker and the best-days/popularity chart (spec's "date-strip picker" and "best-days chart" are
the same physical strip, not two strips), reusing spec 004's design tokens throughout.

## Technical Context

**Language/Version**: Python 3.12 (server), TypeScript/React 19 (client, Vite)

**Primary Dependencies**: FastAPI, pandas, scikit-learn (new: `HistGradientBoostingClassifier`
inference), joblib (new); client: existing React/Tailwind v4/daisyUI stack, no new deps

**Storage**: N/A for this feature — reads `data/datasets/enriched_descriptions/*.json` directly
(terrain/lat-lng/features/surfaceTypes fields the Postgres `trails` table doesn't carry — see
research.md decision 2) plus the existing `trail_activity` Postgres table for review-count
confidence signal, and the trained artifact `data/datasets/models/condition_models.joblib`

**Testing**: pytest (server, `server/tests/`), no client test runner currently configured — manual
browser verification via the preview tools

**Target Platform**: Local dev (FastAPI on :8000, Vite on :5173), same as existing endpoints

**Project Type**: Web application (existing `server/` + `client/` split)

**Performance Goals**: No new goals stated; inference must stay well under the existing weather
endpoint's response envelope (single in-process `predict_proba` calls, not a network round trip)

**Constraints**: Server must have zero runtime import of `data/scripts` (existing design rule,
`app/config.py`'s own comment) — the shared flatten module therefore lives in `server/` and
`data/scripts/model/build_training_table.py` takes the (one-directional) dependency on `server/`,
not the reverse. Model artifact was pickled under scikit-learn 1.6.1; the currently-installed
1.9.0 cannot unpickle it (`_RemainderColsList` AttributeError, confirmed) — pin `scikit-learn==1.6.1`.

**Scale/Scope**: One new working endpoint + 2 new panel sections (~6 new server files, ~4 new
client files, edits to 2 existing data/scripts files)

## Constitution Check

*GATE: Must pass before Phase 0 research. Re-checked after Phase 1 design.*

| Principle | Check | Status |
|---|---|---|
| I. Endpoint Separation | `conditions.py` stays its own module/handler; no merge with `trail_info.py` | PASS |
| II. Feature Parity | Shared `server/app/services/feature_flatten.py` used by both `conditions.py` and (via one-directional import) `build_training_table.py` | PASS (design goal of this plan) |
| III. Forecast Horizon | `conditions.py` rejects dates outside `[today, today+15]` before any upstream call, same bound as `weather.py`'s `MAX_FORECAST_DAYS` | PASS |
| IV. Shared Date State | Single `selectedDate` lifted to `App.tsx`'s `PanelState`, read/written by Weather section's stepper and the Day Selection strip | PASS |
| V. Single Continuous Scroll | New sections appended inside the existing scroll container in `TrailPanel.tsx`, no tabs/routes | PASS |
| VI. Popularity Granularity Honesty | Day-of-week popularity only rendered layered on the day-strip pills, never its own chart | PASS |
| VIII. Honest Uncertainty | `ConditionsResponse` gains a `confidence` object (reviewCount + limitedData); UI always renders it alongside probabilities | PASS |
| IX/X. Selective/Scoped Storage | No schema change — the extra terrain fields (`soilDrainageRank` etc.) needed only by the model are read from the enriched-description JSON directly, not added to Postgres as unused-by-anything-else columns | PASS (see research.md decision 2) |

No violations requiring Complexity Tracking.

## Project Structure

### Documentation (this feature)

```text
specs/005-weather-conditions-ui/
├── plan.md              # This file
├── research.md
├── data-model.md
├── quickstart.md
├── contracts/
│   └── conditions-api.md
└── tasks.md              # /speckit-tasks output (not yet generated)
```

### Source Code (repository root)

```text
server/
├── app/
│   ├── config.py                          # unchanged (CONDITION_MODELS_PATH already present)
│   ├── schemas.py                         # + ConditionsConfidence, ConditionsResponse.confidence
│   ├── routers/trails.py                  # unchanged (route already wired)
│   └── services/
│       ├── feature_flatten.py             # NEW - shared row-flattening (Principle II)
│       ├── open_meteo_client.py           # + fetch_forecast_range (history+forecast window)
│       └── conditions.py                  # stub -> real implementation
├── requirements.txt                       # + scikit-learn==1.6.1, joblib
└── tests/
    └── test_conditions.py                 # NEW

data/scripts/
├── model/build_training_table.py          # _flatten_weather/_flatten_terrain/_flatten_description
│                                           # replaced with imports from server's feature_flatten.py
└── enrich/enrich_review.py                # _antecedent_precip_index replaced with the shared import

client/src/
├── api/trails.ts                          # + getTrailWeatherWindow, getTrailConditions, types
├── App.tsx                                # + selectedDate/weather/conditionsByDate panel state
└── components/
    ├── TrailPanel.tsx                     # unchanged (still just a scroll container)
    ├── WeatherSection.tsx                 # NEW
    ├── DaySelectionSection.tsx            # NEW
    └── dayStrip.ts                        # NEW - shared favorability/formatting helpers
```

**Structure Decision**: Existing `server/` (FastAPI) + `client/` (Vite/React) + `data/scripts/`
(offline pipeline) three-way split is unchanged. This feature's only cross-cutting structural
change is the new one-directional dependency `data/scripts` → `server/app/services/feature_flatten`
(see research.md decision 1).

## Complexity Tracking

*No constitution violations — table not needed.*
