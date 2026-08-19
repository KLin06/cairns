import json
import os
import time
from datetime import date as date_cls
from datetime import timedelta

from fastapi import HTTPException

from app.config import ENRICHED_DESCRIPTIONS_DIR
from app.schemas import DailyWeather, ValidRange, WeatherErrorDetail, WeatherResponse
from app.services.open_meteo_client import MAX_FORECAST_DAYS, fetch_forecast

# Reuse fetch_forecast's own retry/backoff (see MAX_RETRIES/RETRY_BASE_DELAY in
# open_meteo.py) rather than adding a second one here - a 429 that survives
# those retries is treated as exhausted, not retried again at this layer.

_CACHE: dict[str, dict] = {}
_CACHE_TTL_SECONDS = 30 * 60  # 15-60 min range from the spec clarification; 30 min midpoint


def _error(status_code: int, error_type: str, message: str, valid_range: ValidRange | None = None) -> HTTPException:
    detail = WeatherErrorDetail(errorType=error_type, message=message, validRange=valid_range)
    return HTTPException(status_code=status_code, detail=detail.model_dump(by_alias=True))


def _get_trail_location(trail_id: str) -> tuple[float, float]:
    path = os.path.join(ENRICHED_DESCRIPTIONS_DIR, f"{trail_id}.json")
    if not os.path.exists(path):
        raise _error(
            404,
            "trail_unavailable",
            f"trail {trail_id!r} has no enriched description - has it been through the enrich pipeline stage?",
        )

    with open(path, "r", encoding="utf-8") as f:
        data = json.load(f)

    lat, lng = data.get("latitude"), data.get("longitude")
    if lat is None or lng is None:
        raise _error(404, "trail_unavailable", f"trail {trail_id!r} has no location on record")
    return lat, lng


def _resolve_and_validate_dates(
    date: date_cls | None, start_date: date_cls | None, end_date: date_cls | None
) -> list[date_cls]:
    if date is not None and (start_date is not None or end_date is not None):
        raise _error(422, "invalid_date_range", "specify either 'date' or 'start_date'+'end_date', not both")
    if (start_date is None) != (end_date is None):
        raise _error(422, "invalid_date_range", "'start_date' and 'end_date' must be given together")
    if start_date is not None and end_date < start_date:
        raise _error(422, "invalid_date_range", "'end_date' must not be before 'start_date'")

    today = date_cls.today()
    # MAX_FORECAST_DAYS is Open-Meteo's forecast_days cap (the *count* of
    # days a single fetch_forecast call returns, starting from today) - so
    # the furthest valid offset from today is MAX_FORECAST_DAYS - 1, not
    # MAX_FORECAST_DAYS itself. Confirmed against the live API: days=16
    # returns today..today+15 (16 days total); days=17 is rejected 400.
    horizon_end = today + timedelta(days=MAX_FORECAST_DAYS - 1)

    if date is not None:
        requested = [date]
    elif start_date is not None:
        requested = [start_date + timedelta(days=n) for n in range((end_date - start_date).days + 1)]
    else:
        requested = [today + timedelta(days=n) for n in range(15)]  # default window: today through today+14

    out_of_range = [d for d in requested if d < today or d > horizon_end]
    if out_of_range:
        raise _error(
            422,
            "invalid_date_range",
            f"requested date(s) outside the valid range: {sorted(d.isoformat() for d in set(out_of_range))}",
            valid_range=ValidRange(**{"from": today.isoformat(), "to": horizon_end.isoformat()}),
        )

    return requested


def _classify_upstream_error(exc: Exception) -> HTTPException:
    status = getattr(getattr(exc, "response", None), "status_code", None)
    if status == 429:
        return _error(503, "upstream_rate_limited", "weather provider is rate-limiting requests; try again shortly")
    return _error(502, "upstream_unavailable", "weather provider returned an unexpected error")


def _get_cached_or_fetch(trail_id: str, lat: float, lng: float) -> list[dict]:
    entry = _CACHE.get(trail_id)
    now = time.time()
    if entry is not None and (now - entry["fetched_at"]) < _CACHE_TTL_SECONDS:
        return entry["records"]

    try:
        records = fetch_forecast(lat, lng, days=MAX_FORECAST_DAYS)
    except Exception as exc:
        raise _classify_upstream_error(exc) from exc

    _CACHE[trail_id] = {"fetched_at": now, "records": records}
    return records


def _validate_complete_window(records: list[dict], requested_dates: list[date_cls]) -> None:
    available = {r["date"] for r in records}
    missing = [d for d in requested_dates if d.isoformat() not in available]
    if missing:
        raise _error(502, "upstream_unavailable", "weather provider returned an incomplete forecast window")


def get_trail_weather(
    trail_id: str,
    date: date_cls | None = None,
    start_date: date_cls | None = None,
    end_date: date_cls | None = None,
) -> WeatherResponse:
    lat, lng = _get_trail_location(trail_id)
    requested_dates = _resolve_and_validate_dates(date, start_date, end_date)

    records = _get_cached_or_fetch(trail_id, lat, lng)
    _validate_complete_window(records, requested_dates)

    by_date = {r["date"]: r for r in records}
    days = [
        DailyWeather(
            date=d.isoformat(),
            tempMaxC=by_date[d.isoformat()].get("temperature_2m_max"),
            tempMinC=by_date[d.isoformat()].get("temperature_2m_min"),
            precipMm=by_date[d.isoformat()].get("precipitation_sum"),
            windMaxKmh=by_date[d.isoformat()].get("windspeed_10m_max"),
            snowCm=by_date[d.isoformat()].get("snowfall_sum"),
        )
        for d in requested_dates
    ]
    return WeatherResponse(trailId=str(trail_id), days=days)
