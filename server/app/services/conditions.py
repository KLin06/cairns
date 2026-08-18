from fastapi import HTTPException

from app.schemas import ConditionsResponse

# TODO (see "Feature reconstruction at inference time" in APP_SPEC.md):
#
# 1. Load condition_models.joblib (app.config.CONDITION_MODELS_PATH) once
#    at startup, not per-request - it's a {"models": {condition: fitted
#    model}, "features": [...], "thresholds": {condition: float}} dict
#    from data/scripts/model/train_model.py. `thresholds` holds each
#    condition's own tuned probability cutoff (picked off its
#    precision-recall curve, not a blanket 0.5 - see _best_threshold in
#    train_model.py) - use it for the response's `predicted` field instead
#    of hardcoding 0.5.
# 2. Fetch weather via fetch_forecast_with_history(lat, lng, date,
#    history_days=7) from data/scripts/enrich/weather/open_meteo.py -
#    returns the same 8-daily-record shape _flatten_weather already
#    expects, confirmed working against live data.
# 3. Flatten that into weather_d0_* ... weather_d7_* columns with the
#    *same* _flatten_weather function build_training_table.py uses - don't
#    reimplement it here, import/share it, or the two will drift.
# 4. Merge in the trail's static terrain_*/trail_* columns from
#    enriched_descriptions/{trailId}.json (same fields
#    trail_info.py already reads) + dayOfYear computed from the request
#    date.
# 5. Build a single-row DataFrame with exactly `features` (from the
#    .joblib) as columns, matching dtypes (categorical columns as pandas
#    `category`, see train_model.py's CATEGORICAL_COLUMNS) - column
#    order/set must match exactly what the model trained on.
# 6. For each condition, model.predict_proba(row)[:, 1] -> probability;
#    probability >= thresholds[condition] -> predicted. condition_dusty
#    won't be in `models` at all (excluded from training, see
#    EXCLUDED_CONDITIONS in train_model.py) - don't expect it in the
#    response.
#
# Stubbed for now so the route/response shape can be wired up and tested
# before the model-inference plumbing is built.


def get_trail_conditions(trail_id: str, date: str) -> ConditionsResponse:
    raise HTTPException(
        status_code=501,
        detail="conditions prediction not implemented yet - see TODO in app/services/conditions.py",
    )
