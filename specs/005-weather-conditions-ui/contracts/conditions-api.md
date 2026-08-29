# Contract: `GET /trails/{trail_id}/conditions`

Extends the already-wired route (`server/app/routers/trails.py`); only `conditions.py`'s
implementation and `schemas.py`'s response shape change.

## Request

`GET /trails/{trail_id}/conditions?date=YYYY-MM-DD`

- `date`: optional, defaults to today (server-local date). Must be within `[today, today + 15]`
  (matches `/weather`'s `MAX_FORECAST_DAYS` bound exactly).

## Success response — 200

```json
{
  "trailId": "10268327",
  "date": "2026-09-01",
  "conditions": {
    "muddy":    { "probability": 0.62, "predicted": true },
    "bugs":     { "probability": 0.71, "predicted": true },
    "icy":      { "probability": 0.03, "predicted": false },
    "slippery": { "probability": 0.41, "predicted": false },
    "flooded":  { "probability": 0.05, "predicted": false },
    "snow":     { "probability": 0.01, "predicted": false }
  },
  "modelVersion": "2026-08-18",
  "confidence": { "reviewCount": 975, "limitedData": false }
}
```

Notes:
- `dusty` never appears (FR-003) — it's simply absent from `model_bundle["models"]`, not filtered
  post-hoc.
- Keys of `conditions` are always a subset of `{bugs, flooded, icy, muddy, slippery, snow}` — never
  hardcode all six on the client; render whatever keys are present.

## Error responses (same `WeatherErrorDetail` shape as `/trails/{trail_id}/weather`)

| Status | `errorType` | When |
|---|---|---|
| 422 | `invalid_date_range` | `date` outside `[today, today+15]`; `validRange` included |
| 404 | `trail_unavailable` | no `enriched_descriptions/{trail_id}.json`, or it has no lat/lng |
| 503 | `upstream_rate_limited` | Open-Meteo 429 after retries exhausted |
| 502 | `upstream_unavailable` | any other upstream failure, or an incomplete forecast window |

```json
{ "detail": { "errorType": "invalid_date_range", "message": "...", "validRange": { "from": "2026-08-29", "to": "2026-09-13" } } }
```

## Frontend consumption

- `WeatherSection` fetches `/weather` once per trail (full window) and `/conditions` per selected
  date (on-demand, cached in `conditionsByDate`).
- `DaySelectionSection` triggers a `/conditions` fetch for every date in the window on trail-open
  (parallel, best-effort — an individual date's failure just leaves that pill unranked, doesn't
  block the others) to compute the strip's favorability coloring.
