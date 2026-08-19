# Implementation Plan: Trailhead Weather Forecast Endpoint

**Branch**: `001-weather-forecast-endpoint` | **Date**: 2026-08-18 | **Spec**: [spec.md](./spec.md)

**Input**: Feature specification from `/specs/001-weather-forecast-endpoint/spec.md`

## Summary

Add `GET /trails/{trail_id}/weather`, returning a day-by-day Open-Meteo forecast (default:
today + 14 days, or a caller-specified date/range) for a trail's location. Reuses the existing
`fetch_forecast`/retry-with-backoff logic in `data/scripts/enrich/weather/open_meteo.py` rather
than reimplementing the Open-Meteo call. Adds an in-process, short-TTL (15–60 min) per-trail
cache so repeated requests during normal date-picker browsing don't re-hit the upstream API.
Rejects past dates and dates beyond Open-Meteo's real forecast horizon outright, and returns a
distinguishable error for request problems vs. upstream problems vs. upstream rate limiting.

## Technical Context

**Language/Version**: Python 3.11+ (matches existing `server/` and `data/scripts/` code)

**Primary Dependencies**: FastAPI, Pydantic (already in `server/requirements.txt`); `curl_cffi`
(currently only in `data/requirements.txt` — needed in `server/requirements.txt` too, see
research.md for why this is a safe, lightweight addition)

**Storage**: N/A — no persistent storage. The short-TTL cache is in-process memory, not a
database; a full Postgres migration was discussed separately and is explicitly out of scope
here (see research.md).

**Testing**: pytest + FastAPI's `TestClient` (industry-standard pairing for FastAPI; no test
framework exists in `server/` yet, this establishes the pattern for future endpoints too)

**Target Platform**: Same as existing server — runs via `uvicorn app.main:app`, consumed by the
Vite client on `localhost:5173` per the existing CORS config in `server/app/main.py`

**Project Type**: Web service (backend-only addition to the existing single FastAPI app —
`server/app/`; no client-side changes in this feature)

**Performance Goals**: Not explicitly specified by the spec. Informal target: interactive
response time for a trip-planning UI (i.e., perceptible latency should come from the upstream
Open-Meteo call, not from this endpoint's own logic) on a cache hit.

**Constraints**:
- Forecast horizon is a hard boundary (Open-Meteo's real ~16-day limit, not a fixed business
  rule) — reject out-of-range requests entirely, per spec FR-005 and constitution Principle III.
- MUST reuse `fetch_forecast`'s existing retry-with-backoff for Open-Meteo 429s rather than
  reimplementing retry logic (explicit in the feature description and constitution Principle II's
  broader "don't reimplement shared logic" spirit, even though II itself is about the training/
  inference model path specifically).
- MUST stay a separate code path from `app/services/conditions.py`'s model-inference logic, per
  constitution Principle I.
- Trail location MUST come only from a trail's existing enrichment output
  (`enriched_descriptions/{trail_id}.json`), never a live external lookup, per constitution
  Principle VII.

**Scale/Scope**: Single new endpoint, single trail per request. Personal/small-scale traffic
(matches the rest of this app) — no need for a distributed cache; in-process memory is
sufficient.

## Constitution Check

*GATE: Must pass before Phase 0 research. Re-check after Phase 1 design.*

| Principle | Check | Result |
|---|---|---|
| I. Endpoint Separation | New endpoint does no model inference and shares no code path with `conditions.py` | PASS |
| II. Feature Parity (Training/Inference) | Not applicable — this endpoint returns raw provider data, not model features | N/A |
| III. Forecast Horizon Hard Boundary | Spec FR-005/FR-006 reject out-of-range dates outright, no degradation/estimation | PASS |
| IV. Shared Date State (UI) | Not applicable — backend-only feature, no UI state | N/A |
| V. Single Continuous Scroll (UI) | Not applicable — no UI in this feature | N/A |
| VI. Popularity Granularity Honesty | Not applicable — no popularity data involved | N/A |
| VII. Pipeline-Gated Trail Data | Location sourced only from `enriched_descriptions/`, same as `trail_info.py`; unenriched trails rejected (spec FR-007) | PASS |
| VIII. Honest Uncertainty in Predictions | Not applicable — this endpoint returns raw forecast data, not a prediction/probability | N/A |

No violations. Complexity Tracking table is not needed.

**Post-implementation re-check (T023, 2026-08-18)**: Verified against the finished code, not just
the plan. `server/app/services/weather.py` has no import of and shares no logic with
`server/app/services/conditions.py` (Principle I holds). `_get_trail_location` reads only
`enriched_descriptions/{trail_id}.json`, never a live external source (Principle VII holds).
`_resolve_and_validate_dates` rejects any out-of-range date with `validRange` echoed back,
verified live against the real Open-Meteo API — no degraded/estimated response path exists
(Principle III holds). No drift introduced during implementation. II/IV/V/VI/VIII remain N/A as
originally assessed.

## Project Structure

### Documentation (this feature)

```text
specs/001-weather-forecast-endpoint/
├── plan.md              # This file
├── research.md          # Phase 0 output
├── data-model.md         # Phase 1 output
├── quickstart.md         # Phase 1 output
├── contracts/            # Phase 1 output
│   └── weather-endpoint.md
└── tasks.md              # Phase 2 output (/speckit-tasks — not created here)
```

### Source Code (repository root)

```text
server/
├── app/
│   ├── config.py                    # add sys.path bridge to data/ (see research.md)
│   ├── main.py                      # unchanged
│   ├── schemas.py                   # add DailyWeather, WeatherResponse, WeatherErrorDetail
│   ├── routers/
│   │   └── trails.py                # add GET /weather route, alongside /info /conditions /activity /geometry
│   └── services/
│       └── weather.py               # NEW — mirrors trail_info.py/conditions.py's one-module-per-endpoint pattern
├── requirements.txt                 # add curl_cffi
└── tests/                           # NEW — no test dir exists yet; this feature establishes it
    └── test_weather.py

data/scripts/enrich/weather/open_meteo.py   # unchanged — reused, not modified
```

**Structure Decision**: Single-project structure (existing `server/app/` layout). This feature
adds one router endpoint, one service module, two schema additions, and a `tests/` directory —
no new top-level projects or restructuring. The only structural first: `server/` gaining a real
import path into `data/scripts/` (see research.md), since no prior endpoint has needed to reuse
pipeline code at request time.

## Complexity Tracking

*No constitution violations — table not needed.*
