# Contract: `GET /trails/{trail_id}/weather`

Follows the same router/response-model convention as the existing endpoints in
`server/app/routers/trails.py` (`/info`, `/conditions`, `/activity`, `/geometry`).

## Request

`GET /trails/{trail_id}/weather`

Query parameters (all optional; see data-model.md's `ForecastRequest` validation rules):
- `date` — single date, `YYYY-MM-DD`
- `start_date` / `end_date` — range, `YYYY-MM-DD`, inclusive, must be given together

No date parameters → default window (today through today+14).

## Success response — `200 OK`

```json
{
  "trailId": "10268327",
  "days": [
    {
      "date": "2026-08-20",
      "tempMaxC": 24.1,
      "tempMinC": 12.3,
      "precipMm": 3.2,
      "windMaxKmh": 18.4,
      "snowCm": 0.0
    }
  ]
}
```

Pydantic model: `WeatherResponse` (see data-model.md).

## Error responses

All error bodies share the `WeatherErrorDetail` shape (see data-model.md), returned as the
`detail` of a FastAPI `HTTPException`.

### `422 Unprocessable Entity` — invalid/out-of-range date(s)

Covers: date in the past, date beyond the provider's real forecast horizon, or a range where
either endpoint is invalid (spec FR-004, FR-005, User Story 3).

```json
{
  "errorType": "invalid_date_range",
  "message": "requested date 2026-09-15 is beyond the forecast horizon",
  "validRange": { "from": "2026-08-18", "to": "2026-09-03" }
}
```

### `404 Not Found` — trail has no known location

Covers: trail never enriched, or trail ID unknown entirely (spec FR-007, Edge Cases). Matches
the existing 404 convention `trail_info.py` already uses for missing enrichment data.

```json
{
  "errorType": "trail_unavailable",
  "message": "trail '99999999' has no enriched description - has it been through the enrich pipeline stage?",
  "validRange": null
}
```

### `503 Service Unavailable` — upstream rate-limited (retries exhausted)

Covers: `fetch_forecast`'s own retry/backoff (in `data/scripts/enrich/weather/open_meteo.py`)
exhausted its attempts against a 429 (spec FR-009, User Story 4 Scenario 1).

```json
{
  "errorType": "upstream_rate_limited",
  "message": "weather provider is rate-limiting requests; try again shortly",
  "validRange": null
}
```

### `502 Bad Gateway` — other upstream failure

Covers: any other failure reaching/parsing the upstream provider's response (spec FR-008,
User Story 4 Scenario 2).

```json
{
  "errorType": "upstream_unavailable",
  "message": "weather provider returned an unexpected error",
  "validRange": null
}
```

## Non-goals (explicitly out of this contract)

- No derived/predicted trail conditions — raw provider data only (constitution Principle I).
- No historical/past-date weather — this contract only serves forecast dates (spec FR-004).
- No batching multiple trails per request.
