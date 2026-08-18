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
- `GET /trails/{trail_id}/conditions` - **stubbed**, returns 501. See the
  TODO in `app/services/conditions.py` for what's left (forecast fetch +
  feature reconstruction + model inference).
