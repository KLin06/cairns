# Quickstart: Validating Weather & Predicted Conditions UI

## Prerequisites

- `server/venv` has `scikit-learn==1.6.1` and `joblib` installed (added to `server/requirements.txt`
  by this feature — run `pip install -r requirements.txt` if your venv predates this change).
- `data/datasets/models/condition_models.joblib` exists (already committed as of this feature's
  branch point).
- At least one trail under `data/datasets/enriched_descriptions/` with a valid `latitude`/`longitude`.
- Postgres reachable per `server/.env`'s `DATABASE_URL` (only needed for the `reviewCount`
  confidence signal via `trail_activity` — conditions still returns predictions with
  `limitedData: true` if this trail has no activity row).

## Backend

```bash
cd server
venv/Scripts/activate  # or source venv/bin/activate
uvicorn app.main:app --reload
```

```bash
curl "http://localhost:8000/trails/<a-real-trail-id>/conditions"
curl "http://localhost:8000/trails/<a-real-trail-id>/conditions?date=2099-01-01"   # expect 422 invalid_date_range
curl "http://localhost:8000/trails/00000000/conditions"                            # expect 404 trail_unavailable
```

Expected: the first call returns a `conditions` object with a subset of
`{bugs, flooded, icy, muddy, slippery, snow}`, each with `probability`/`predicted`, plus
`confidence` and `modelVersion` — never a bare probability with no `confidence` object (SC-002).

```bash
cd server
pytest tests/test_conditions.py -v
```

## Frontend

```bash
cd client
npm run dev
```

Open the app, click a trail marker with a valid location, scroll the panel past Overview:

1. **Weather section** renders with today already selected (raw weather + predicted conditions
   side by side), each independently loading (FR-013) rather than one blocking spinner.
2. Any flagged condition shows a prep suggestion (e.g. muddy → "Waterproof boots recommended").
3. A confidence line is always visible next to the predictions (e.g. "based on 975 historical
   reports" or "limited data for this trail").
4. **Day Selection section** below it renders a ~16-day strip, each pill colored by that day's
   favorability with a popularity indicator layered on (not a separate chart).
5. Tap a different pill → Weather section above updates to that date without scrolling away or a
   full reload (SC-001, SC-003) — verify via the day-stepper in the Weather section moving too.
6. Rapidly tap several pills before responses can return → only the last-tapped date's response
   ever renders (FR-020) — no flicker back to an earlier day's numbers.
7. Days beyond the forecast horizon are visibly disabled on the strip and not tappable (FR-018).

`tsc --noEmit` and `eslint` should both be clean on the changed client files.
