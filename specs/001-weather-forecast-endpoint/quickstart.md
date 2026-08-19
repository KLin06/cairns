# Quickstart: Validating the Weather Forecast Endpoint

## Prerequisites

- A trail that has already gone through the enrich pipeline stage, i.e. has a file at
  `data/datasets/enriched_descriptions/{trail_id}.json` with `latitude`/`longitude` present.
  (Any trail `trail_info.py` already serves successfully works — see `server/README.md`'s
  Status section for confirmation `/info` is working.)
- `server/requirements.txt` installed, including the `curl_cffi` addition from this feature.

## Run the server

```bash
cd server
venv/Scripts/activate   # or source venv/bin/activate on macOS/Linux
uvicorn app.main:app --reload
```

## Scenario 1 — default 14-day window (User Story 1)

```bash
curl http://localhost:8000/trails/{trail_id}/weather
```

**Expected**: `200 OK`, `days` contains 15 entries (today through today+14), date-sorted,
starting from today.

## Scenario 2 — specific date / range (User Story 2)

```bash
curl "http://localhost:8000/trails/{trail_id}/weather?date=2026-08-25"
curl "http://localhost:8000/trails/{trail_id}/weather?start_date=2026-08-20&end_date=2026-08-24"
```

**Expected**: first call returns exactly one `days` entry for 2026-08-25; second returns 5
entries covering the inclusive range.

## Scenario 3 — rejecting out-of-range dates (User Story 3)

```bash
curl -i "http://localhost:8000/trails/{trail_id}/weather?date=2026-08-01"   # a past date
curl -i "http://localhost:8000/trails/{trail_id}/weather?date=2027-01-01"   # far beyond horizon
```

**Expected**: both return `422`, body `errorType: "invalid_date_range"`, with `validRange`
telling you the actual valid window — no `days` data in either response.

## Scenario 4 — unknown/unenriched trail (Edge Case)

```bash
curl -i "http://localhost:8000/trails/00000000/weather"
```

**Expected**: `404`, `errorType: "trail_unavailable"`.

## Scenario 5 — cache behavior (spec SC-005)

```bash
curl "http://localhost:8000/trails/{trail_id}/weather" > /dev/null
curl "http://localhost:8000/trails/{trail_id}/weather?date=2026-08-22" > /dev/null
```

**Expected**: only the first call actually reaches Open-Meteo (observable via server logs/a
breakpoint in `fetch_forecast`, or by temporarily logging cache hits in `weather.py` during
manual verification) — the second call, for a date already covered by the first call's cached
window, is served from cache.

## Scenario 6 — upstream failure distinction (User Story 4)

Not reproducible against the real Open-Meteo API on demand. Validate via the pytest suite
(`server/tests/test_weather.py`), which monkeypatches `fetch_forecast` to raise a
rate-limit-exhausted condition and a generic failure separately, asserting `503` vs `502`
respectively.

```bash
cd server
pytest tests/test_weather.py -v
```
