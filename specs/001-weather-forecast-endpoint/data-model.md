# Phase 1 Data Model: Trailhead Weather Forecast Endpoint

No persistent storage is introduced (see research.md #2) — these are the in-memory/response
shapes involved, not database tables.

## ForecastRequest (implicit — query parameters, not a stored entity)

| Field | Type | Required | Notes |
|---|---|---|---|
| `trail_id` | string | yes (path param) | Same `trail_id` convention as existing endpoints |
| `date` | date (`YYYY-MM-DD`) | no | Single-date request; mutually exclusive with `start_date`/`end_date` |
| `start_date` | date (`YYYY-MM-DD`) | no | Range request start (inclusive) |
| `end_date` | date (`YYYY-MM-DD`) | no | Range request end (inclusive) |

Validation rules (from spec FR-002 through FR-006):
- If none of `date`/`start_date`/`end_date` given → default window = today through today+14.
- `date` and `start_date`/`end_date` are mutually exclusive.
- If `start_date` given, `end_date` must also be given (and vice versa).
- Every resolved date in the request MUST be `>= today` and `<= <today> + MAX_FORECAST_DAYS>`
  (16 days — the constant added to `open_meteo.py` alongside the existing
  `MAX_FORECAST_PAST_DAYS`, which governs a different, backward-looking boundary — see
  research.md #1). Any date outside this range invalidates the *whole* request (spec FR-004,
  FR-005, User Story 3 Scenario 3) — no partial responses.

## TrailLocation (read, not owned by this feature)

| Field | Type | Source |
|---|---|---|
| `lat` | float | `enriched_descriptions/{trail_id}.json` — same field `trail_info.py` already reads |
| `lng` | float | `enriched_descriptions/{trail_id}.json` |

If the trail has no enrichment output on disk, the request is rejected as `trail_unavailable`
(spec FR-007) — this feature does not compute or trigger enrichment.

## DailyWeather (response item)

Mirrors APP_SPEC.md's draft `GET /trails/:trailId/weather` shape:

| Field | Type | Source (from `fetch_forecast`'s raw record) |
|---|---|---|
| `date` | string (`YYYY-MM-DD`) | `date` |
| `tempMaxC` | float | `temperature_2m_max` |
| `tempMinC` | float | `temperature_2m_min` |
| `precipMm` | float | `precipitation_sum` |
| `windMaxKmh` | float | `windspeed_10m_max` |
| `snowCm` | float | `snowfall_sum` |

## WeatherResponse (top-level response)

| Field | Type |
|---|---|
| `trailId` | string |
| `days` | list of `DailyWeather`, date-sorted |

## WeatherErrorDetail (error response body)

| Field | Type | Values |
|---|---|---|
| `errorType` | string enum | `invalid_date_range`, `trail_unavailable`, `upstream_rate_limited`, `upstream_unavailable` |
| `message` | string | Human-readable explanation |
| `validRange` | object (`{"from": date, "to": date}`) or null | Present only for `invalid_date_range`, per spec FR-006 |

## CacheEntry (internal, in-process — not part of the API contract)

| Field | Type | Notes |
|---|---|---|
| `trail_id` | string | Cache key |
| `fetched_at` | datetime | Used against the 30-min TTL (research.md #2) |
| `records` | list of `DailyWeather`-shaped dicts | The full fetched window, sliced per-request |
