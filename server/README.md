# Server

FastAPI backend for the trail conditions app. Reads whatever
`data/scripts/...` (the scrape/clean/enrich pipeline) has already produced
on disk under `data/datasets/` - this app doesn't run any pipeline stages
itself.

See `../APP_SPEC.md` for the API contract and design notes.

## Run

```bash
python -m venv venv
venv/Scripts/activate   # or source venv/bin/activate on macOS/Linux
pip install -r requirements.txt
uvicorn app.main:app --reload
```

Then visit `http://localhost:8000/docs` for the interactive API docs
(FastAPI auto-generates this from the Pydantic schemas in `app/schemas.py`).

## Status

- `GET /trails/{trail_id}/info` - working, reads `enriched_descriptions/`
  + `cleaned_reviews/`.
- `GET /trails/{trail_id}/activity` - working, aggregates
  `cleaned_reviews/` dates.
- `python -m db.backfill [trail_id ...]` - populates the `trails` /
  `trail_activity` / `trail_geometry` Postgres tables
  (`db/migrations/0001_trail_data_storage.sql`) from the same
  `data/datasets/` pipeline output the endpoints above already read, reusing
  their derivation logic. Safe to re-run (upserts, skips unchanged rows); a
  trail with no `enriched_descriptions/{trail_id}.json` is skipped, not an
  error. See `specs/003-trail-storage-backfill/contracts/cli.md`.
- `GET /trails/{trail_id}/weather` - working, reuses
  `data/scripts/enrich/weather/open_meteo.py`'s `fetch_forecast` (see
  `specs/001-weather-forecast-endpoint/`). Default window is today through
  +14 days; accepts `date` or `start_date`/`end_date` instead. Rejects past
  dates and dates beyond Open-Meteo's ~16-day horizon with `422`; an
  unenriched trail returns `404`; upstream failures return `502`/`503`
  depending on whether they were rate-limiting. Short-TTL (30 min)
  in-process cache per trail.
- `GET /trails/{trail_id}/conditions` - **stubbed**, returns 501. See the
  TODO in `app/services/conditions.py` for what's left (forecast fetch +
  feature reconstruction + model inference).

## Tests

```bash
pytest
```
