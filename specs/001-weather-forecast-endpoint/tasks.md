---
description: "Task list for the Trailhead Weather Forecast Endpoint feature"
---

# Tasks: Trailhead Weather Forecast Endpoint

**Input**: Design documents from `/specs/001-weather-forecast-endpoint/`

**Prerequisites**: [plan.md](./plan.md), [spec.md](./spec.md), [research.md](./research.md), [data-model.md](./data-model.md), [contracts/weather-endpoint.md](./contracts/weather-endpoint.md)

**Tests**: Included — plan.md's Technical Context commits to pytest + FastAPI `TestClient`, and quickstart.md Scenario 6 depends on `server/tests/test_weather.py` existing (upstream-failure cases aren't reproducible against the real Open-Meteo API on demand).

**Organization**: Tasks are grouped by user story (from spec.md, priority order) to enable independent implementation and testing of each story.

## Format: `[ID] [P?] [Story] Description`

- **[P]**: Can run in parallel (different files, no dependencies)
- **[Story]**: Which user story this task belongs to (US1–US4, per spec.md)

## Path Conventions

Single project, existing `server/app/` layout (per plan.md's Structure Decision) — no new top-level projects.

---

## Phase 1: Setup

**Purpose**: Dependencies and test scaffolding

- [x] T001 Add `curl_cffi` and `pytest` to `server/requirements.txt` (research.md #1, #4)
- [x] T002 [P] Create `server/tests/__init__.py` and an empty `server/tests/test_weather.py` importing FastAPI's `TestClient` from `app.main`

---

## Phase 2: Foundational (Blocking Prerequisites)

**Purpose**: Shared infrastructure every user story depends on

**⚠️ CRITICAL**: No user story task can begin until this phase is complete

- [x] T003 Add a `sys.path` bridge to `data/` in `server/app/config.py` (alongside the existing `REPO_ROOT`/`DATASETS_DIR` constants) so `from scripts.enrich.weather.open_meteo import fetch_forecast, MAX_FORECAST_DAYS` resolves (research.md #1)
- [x] T003a Add `MAX_FORECAST_DAYS = 16` to `data/scripts/enrich/weather/open_meteo.py` alongside the existing `MAX_FORECAST_PAST_DAYS` — the future-looking forecast horizon previously had no named constant, only a docstring comment (research.md #1 remediation). **Already applied.**
- [x] T004 [P] Add `DailyWeather`, `WeatherResponse`, and `WeatherErrorDetail` Pydantic models to `server/app/schemas.py`, matching data-model.md's field tables
- [x] T005 [P] Add a trail-location lookup helper to `server/app/services/weather.py` that reads `lat`/`lng` from `enriched_descriptions/{trail_id}.json` (same file/pattern `_load_json` in `server/app/services/trail_info.py` already uses) and raises a `trail_unavailable`-typed `HTTPException(404, ...)` if missing
- [x] T006 Add an in-process per-trail cache (`dict` keyed by `trail_id`, storing `fetched_at` + the full fetched window, 30-minute TTL) to `server/app/services/weather.py`, with a `_get_cached_or_fetch(trail_id, lat, lng)` helper that calls `fetch_forecast` only on a cache miss/expiry (research.md #2)
- [x] T006a [P] Contract test in `server/tests/test_weather.py`: mock `fetch_forecast` with a call counter, make two requests for the same trail with overlapping date windows, and assert `fetch_forecast` was called exactly once — verifies spec SC-005 (previously only checkable manually per quickstart.md Scenario 5)
- [x] T007 Register `GET /weather` on the existing `trail_id`-scoped router in `server/app/routers/trails.py`, alongside `/info`, `/conditions`, `/activity`, `/geometry`, wired to a not-yet-implemented `get_trail_weather(...)` in `weather.py`

**Checkpoint**: Foundation ready — user story implementation can now begin

---

## Phase 3: User Story 1 - Default upcoming forecast (Priority: P1) 🎯 MVP

**Goal**: A caller can request a trail's forecast with no date parameters and get today through today+14, date-sorted.

**Independent Test**: `GET /trails/{trail_id}/weather` with no query params on a fully-enriched trail returns `200` with 15 date-sorted `days` entries starting today.

### Tests for User Story 1

- [x] T008 [P] [US1] Contract test in `server/tests/test_weather.py`: no-params request on a known/mocked trail returns `200` with 15 date-sorted `days` entries starting today (mock `fetch_forecast` to avoid a real network call, per contracts/weather-endpoint.md)

### Implementation for User Story 1

- [x] T009 [US1] Implement `get_trail_weather(trail_id)` default-window path in `server/app/services/weather.py`: resolve location (T005), fetch/cache the window via `_get_cached_or_fetch` (T006), return today→today+14 as `WeatherResponse`
- [x] T010 [US1] Wire the default-window response into the `GET /weather` route in `server/app/routers/trails.py`
- [x] T011 [US1] Confirm the `trail_unavailable` 404 path (T005) is reachable end-to-end through the route for an unenriched `trail_id` (spec FR-007, Edge Cases)

**Checkpoint**: `GET /trails/{trail_id}/weather` is fully functional for the default-window case, independently testable and demoable.

---

## Phase 4: User Story 2 - Specific date or date range (Priority: P1)

**Goal**: A caller can request a single date or an explicit date range instead of the default window.

**Independent Test**: `?date=YYYY-MM-DD` returns exactly one `days` entry for that date; `?start_date=...&end_date=...` returns one entry per day in the inclusive range.

### Tests for User Story 2

- [x] T012 [P] [US2] Contract tests in `server/tests/test_weather.py`: single `date` param returns exactly one matching entry; `start_date`/`end_date` range returns the full inclusive set; `date` combined with `start_date`/`end_date` is rejected as a malformed request

### Implementation for User Story 2

- [x] T013 [US2] Add `date`, `start_date`, `end_date` query parameters to the `GET /weather` route in `server/app/routers/trails.py`, enforcing the mutual-exclusivity/pairing rule from data-model.md's `ForecastRequest`
- [x] T014 [US2] Extend `get_trail_weather(...)` in `server/app/services/weather.py` to accept an explicit single date or date range and slice the cached/fetched window accordingly (reusing T009's cache path, not a separate fetch path)

**Checkpoint**: Both default-window and explicit date/range requests work independently; US1 still passes.

---

## Phase 5: User Story 3 - Rejecting out-of-range date requests (Priority: P2)

**Goal**: Past dates and dates beyond Open-Meteo's real forecast horizon are rejected outright, whole-request, with the valid range communicated back.

**Independent Test**: A past `date` and a far-future `date` are each rejected `422` with `errorType: "invalid_date_range"` and a populated `validRange`; a range straddling the valid/invalid boundary is rejected entirely, not partially served.

### Tests for User Story 3

- [x] T015 [P] [US3] Contract tests in `server/tests/test_weather.py`: past date → `422`; date beyond the horizon → `422` with `validRange` populated; range with only one endpoint out-of-bounds → `422`, no `days` data returned (per contracts/weather-endpoint.md and spec FR-004–FR-006, User Story 3 Scenario 3)

### Implementation for User Story 3

- [x] T016 [US3] Implement date-range validation in `server/app/services/weather.py`: reject if any requested date is `< today` or `> today + MAX_FORECAST_DAYS` (import `MAX_FORECAST_DAYS` — the 16-day future horizon constant added to `open_meteo.py` in T003a; do NOT use `MAX_FORECAST_PAST_DAYS`, which governs an unrelated backward-looking boundary — research.md #1, spec Assumptions), raising `invalid_date_range` with `validRange` populated
- [x] T017 [US3] Ensure validation runs against the *entire* resolved date set before any fetch/cache lookup happens, so a partially-invalid range never reaches a partial response (spec FR-004, FR-010)

**Checkpoint**: All three date-handling stories (US1, US2, US3) work together and independently.

---

## Phase 6: User Story 4 - Distinguishing request errors from upstream failures (Priority: P2)

**Goal**: A caller can tell, from the error response alone, whether a failure was their own bad request, an unavailable upstream provider, or specifically upstream rate limiting.

**Independent Test**: With `fetch_forecast` mocked to simulate retries-exhausted-on-429, the response is `503`/`upstream_rate_limited`; mocked to raise any other failure, the response is `502`/`upstream_unavailable`; distinct from the `422`/`404` cases in US1/US3.

### Tests for User Story 4

- [x] T018 [P] [US4] Contract tests in `server/tests/test_weather.py`: monkeypatch `fetch_forecast` to raise a rate-limit-exhausted condition → assert `503` + `errorType: "upstream_rate_limited"`; monkeypatch to raise a different exception → assert `502` + `errorType: "upstream_unavailable"`; monkeypatch to return fewer days than requested (no exception) → assert `502` + `errorType: "upstream_unavailable"` (contracts/weather-endpoint.md; spec Edge Cases)

### Implementation for User Story 4

- [x] T019 [US4] In `server/app/services/weather.py`, catch failures from `_get_cached_or_fetch`/`fetch_forecast` and classify them into `upstream_rate_limited` (429/retries-exhausted) vs `upstream_unavailable` (anything else), per research.md #3's mapping
- [x] T019a [US4] In `server/app/services/weather.py`, after a successful `fetch_forecast` call, verify the returned window's day-count actually covers every requested date; if Open-Meteo returned a partial/incomplete window (fewer days than requested, no exception raised), raise `upstream_unavailable` rather than returning a response that looks complete but silently has missing days (spec Edge Cases, FR-010)
- [x] T020 [US4] Wire the classified upstream errors into `HTTPException(503, ...)` / `HTTPException(502, ...)` responses reachable through the `GET /weather` route in `server/app/routers/trails.py`

**Checkpoint**: All four user stories work independently and together — the endpoint is feature-complete per spec.md.

---

## Phase 7: Polish & Cross-Cutting Concerns

**Purpose**: Wrap-up that spans all stories

- [x] T021 [P] Update `server/README.md`'s Status section to list `GET /trails/{trail_id}/weather` as working, matching the existing entries for `/info` and `/activity`
- [x] T022 Run all six scenarios in `quickstart.md` against a locally running server (`uvicorn app.main:app --reload`) to confirm end-to-end behavior, not just the mocked unit tests
- [x] T023 [P] Re-check the Constitution Check table in `plan.md` (Principles I, III, VII) against the finished implementation and confirm no drift was introduced during coding

---

## Dependencies & Execution Order

### Phase Dependencies

- **Setup (Phase 1)**: No dependencies — start immediately
- **Foundational (Phase 2)**: Depends on Setup — BLOCKS all user stories
- **User Story 1 (Phase 3)**: Depends on Foundational only
- **User Story 2 (Phase 4)**: Depends on Foundational; builds on US1's `get_trail_weather`/cache path (T009) but is independently testable once T013–T014 land
- **User Story 3 (Phase 5)**: Depends on Foundational; adds validation ahead of the fetch/cache path US1/US2 already use — independently testable via T015 even before US2 is done, since it only needs a single-`date` request
- **User Story 4 (Phase 6)**: Depends on Foundational; independently testable via mocked failures regardless of US2/US3 status
- **Polish (Phase 7)**: Depends on all four user stories being complete

### Parallel Opportunities

- T002 (test scaffolding) can run alongside T001 (requirements.txt)
- T004 and T005 (schemas vs. location helper) touch different files and can run in parallel once T003 lands
- Each story's contract-test task (T008, T012, T015, T018) can be written in parallel with the others, since they're additive to the same test file but target independent scenarios
- Once Foundational (Phase 2) is done, US3 and US4 have no real dependency on US1/US2 completion and could be implemented out of priority order if needed — priority order (P1s first) is still the recommended path since US1 is the MVP

---

## Implementation Strategy

### MVP First (User Story 1 Only)

1. Phase 1 (Setup) → Phase 2 (Foundational) → Phase 3 (US1)
2. **STOP and VALIDATE**: run T008, confirm the default-window request works end-to-end
3. This alone is a demoable MVP: a trail's upcoming forecast, no error-hardening yet

### Incremental Delivery

1. Setup + Foundational → foundation ready
2. US1 → default window works (MVP)
3. US2 → callers can target specific dates (needed before the date-picker UI feature can consume this endpoint meaningfully)
4. US3 → out-of-range requests fail safely instead of silently
5. US4 → failure modes become debuggable/distinguishable
6. Polish → docs + full quickstart pass + constitution re-check

## Notes

- No `[Story]` label on Setup/Foundational/Polish tasks, per the checklist format rules.
- All contract tests mock `fetch_forecast` rather than hitting the real Open-Meteo API (consistent with research.md #4's testing decision) — none of this suite makes real network calls.
- Commit after each task or logical group; verify each story's contract test passes before moving to the next story's implementation tasks.
