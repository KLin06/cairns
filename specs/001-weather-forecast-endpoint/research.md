# Phase 0 Research: Trailhead Weather Forecast Endpoint

## 1. How does `server/` get Open-Meteo forecast data?

**Decision (revised)**: `server/app/services/open_meteo_client.py` is a small, self-contained
Open-Meteo client living entirely in `server/` — `fetch_forecast`, its 429 retry/backoff, and the
`MAX_FORECAST_DAYS = 16` constant, with no import of or `sys.path` dependency on `data/scripts`.

**Original decision (superseded)**: an earlier version of this feature imported
`data/scripts/enrich/weather/open_meteo.py` directly via a `sys.path` bridge in
`server/app/config.py`, to reuse the pipeline's existing retry/backoff logic rather than
duplicate it. That worked and was verified end-to-end, but was explicitly reversed per project
direction: `server/` must run standalone with no runtime dependency on `data/scripts`'s Python
code, even at the cost of duplicating the ~30 lines of fetch/retry logic. The retry/backoff
behavior (`MAX_RETRIES`, `RETRY_BASE_DELAY`) is intentionally mirrored, not shared — a comment in
`open_meteo_client.py` notes this so the duplication is a visible, deliberate tradeoff rather than
silent drift. `curl_cffi` is still a `server/requirements.txt` dependency, now used directly
rather than transitively.

`MAX_FORECAST_DAYS = 16` also now lives only in `server/app/services/open_meteo_client.py` — the
copy previously added to `data/scripts/enrich/weather/open_meteo.py` was left in place there too
(harmless, accurate documentation of the pipeline's own `fetch_forecast`'s real limit), but is no
longer imported by the server.

**Alternatives considered**:
- *Keep the `sys.path` bridge into `data/scripts`* — this was the original decision; reversed per
  explicit direction that `server/`'s Python files must work standalone with no imports from
  `data/`.
- *Package `data/scripts` as an installable package* — still not pursued, same reasoning as
  before, and now moot for this feature since `server/` no longer imports pipeline code at all.

## 2. Cache design for the 15–60 min short-TTL requirement (spec FR-011)

**Decision**: A single in-process `dict` keyed by `trail_id`, storing `{"fetched_at": <time>,
"records": [...]}` for the maximal forecast window (today through the provider's real horizon,
fetched once). A request for any specific date or sub-range is served by slicing the cached
records, re-fetching only if the cache entry is missing, expired (>TTL since `fetched_at`), or
somehow doesn't cover the whole requested range. TTL: 30 minutes (midpoint of the 15–60 min
range from the clarification answer).

**Rationale**: Fetching and caching the *whole* available window per trail (rather than caching
per exact requested range) means a caller browsing different dates in the date-picker UI
(spec User Story 2) hits the cache on every date within the window, not just on exact-repeat
requests — directly serving spec SC-005's "at most one upstream call per trail per window"
outcome. A plain in-process dict is sufficient given the single-process, personal-scale
deployment noted in Technical Context — no need for Redis or another external cache store.

**Alternatives considered**:
- *Cache per exact (trail_id, date_range) request* — rejected: two requests for overlapping but
  non-identical ranges (e.g., "today+14" then "today+10") would both miss, defeating the point.
- *External cache (Redis, etc.)* — rejected as over-engineering for current single-process scale;
  revisit if the backend ever runs multi-process/multi-instance.

## 3. Error response shape for distinguishing failure kinds (spec FR-008/FR-009)

**Decision**: Add a `WeatherErrorDetail` schema with an `errorType` field, one of:
`"invalid_date_range"`, `"trail_unavailable"`, `"upstream_rate_limited"`,
`"upstream_unavailable"`. Map to HTTP status codes:
- `invalid_date_range` → 422 (matches FastAPI's own validation-error convention)
- `trail_unavailable` → 404 (matches the existing pattern in `trail_info.py`)
- `upstream_rate_limited` → 503, after `fetch_forecast`'s own retries are exhausted
- `upstream_unavailable` → 502, for any other upstream failure

**Rationale**: Status code alone (422 vs 404 vs 502 vs 503) already gives callers a
machine-distinguishable signal without needing to parse a message string, satisfying spec SC-003
and SC-004 directly. Including `errorType` explicitly in the body (rather than relying on status
code alone) makes the distinction self-documenting in the OpenAPI schema FastAPI auto-generates,
which matches this project's existing habit of deriving `/docs` straight from Pydantic schemas
(per `server/README.md`).

**Alternatives considered**:
- *Status code only, no structured body* — rejected: 503 alone doesn't distinguish "rate limited"
  from "some other upstream failure," which spec FR-009 explicitly requires distinguishing.
- *Single generic 500 for all upstream failures* — rejected outright by spec FR-008.

## 4. Testing approach

**Decision**: pytest + FastAPI's `TestClient`, with the Open-Meteo call itself mocked/monkeypatched
(no real network calls in tests) to simulate success, rate-limit-exhausted, and other-failure
cases.

**Rationale**: `TestClient` is FastAPI's own documented testing tool and requires no new
dependency beyond `httpx` (already a transitive dependency of FastAPI). No test suite exists in
`server/` yet, so this establishes the pattern future endpoints (conditions, activity, geometry)
can follow. Mocking the upstream call is necessary regardless of framework choice, since spec
User Story 4's rate-limit/failure scenarios can't be reliably reproduced against the real
Open-Meteo API in a test run.

**Alternatives considered**: none seriously — this is the standard, low-friction choice for a
FastAPI project with no prior test infrastructure to be consistent with.

---

All `NEEDS CLARIFICATION` items from Technical Context are resolved above. No open questions
remain before Phase 1 design.
