import json

from curl_cffi import requests

from dateutils import shift_days, to_date, today

FORECAST_URL = "https://api.open-meteo.com/v1/forecast"
ARCHIVE_URL = "https://archive-api.open-meteo.com/v1/archive"

ARCHIVE_LAG_DAYS = 5  # ERA5 archive isn't finalized for the last ~5 days
MAX_FORECAST_PAST_DAYS = 92  # Open-Meteo forecast endpoint's past-data limit

DAILY_VARS = [
    "temperature_2m_max",
    "temperature_2m_min",
    "precipitation_sum",
    "rain_sum",
    "snowfall_sum",
    "windspeed_10m_max",
]
CURRENT_VARS = [
    "temperature_2m",
    "precipitation",
    "rain",
    "snowfall",
    "windspeed_10m",
    "weathercode",
]


def _get(url, params):
    resp = requests.get(url, params=params, timeout=30)
    resp.raise_for_status()
    return resp.json()


def _zip_daily(daily):
    """Turn Open-Meteo's columnar {var: [v1, v2, ...], time: [d1, d2, ...]}
    shape into one dict per date: [{"date": d1, var: v1, ...}, ...]."""
    dates = daily["time"]
    fields = {k: v for k, v in daily.items() if k != "time"}
    return [
        {"date": date, **{field: values[i] for field, values in fields.items()}}
        for i, date in enumerate(dates)
    ]


def fetch_current_weather(lat, lng):
    """Current conditions (temp, precipitation, wind, etc.) at a point."""
    params = {
        "latitude": lat,
        "longitude": lng,
        "current": ",".join(CURRENT_VARS),
        "timezone": "auto",
    }
    return _get(FORECAST_URL, params)["current"]


def fetch_forecast(lat, lng, days=7):
    """Daily forecast (up to 16 days out) at a point, as a date-sorted list
    of per-day records."""
    params = {
        "latitude": lat,
        "longitude": lng,
        "daily": ",".join(DAILY_VARS),
        "forecast_days": days,
        "timezone": "auto",
    }
    return _zip_daily(_get(FORECAST_URL, params)["daily"])


def fetch_historical_weather(lat, lng, start_date, end_date):
    """Historical daily weather (ERA5 reanalysis) at a point, as a
    date-sorted list of per-day records.

    start_date/end_date: "YYYY-MM-DD" strings, inclusive.

    The ERA5 archive isn't finalized for the last ARCHIVE_LAG_DAYS days, and
    has nothing at all for future dates, so:
    - end_date in the future -> raises ValueError, the archive can't answer this.
    - end_date within ARCHIVE_LAG_DAYS of today -> warns and transparently
      falls back to the forecast endpoint's own recent-past data instead,
      which has no such lag (see fetch_forecast_with_history).
    """
    if to_date(end_date) > to_date(today()):
        raise ValueError(
            f"end_date {end_date!r} is in the future - the historical archive "
            "has no data past today; use fetch_forecast/fetch_forecast_with_history instead"
        )

    if (to_date(today()) - to_date(end_date)).days < ARCHIVE_LAG_DAYS:
        print(
            f"warning: end_date {end_date!r} is within {ARCHIVE_LAG_DAYS} days of today - "
            "the ERA5 archive isn't finalized yet, falling back to the forecast endpoint's "
            "recent-past data instead"
        )
        params = {
            "latitude": lat,
            "longitude": lng,
            "start_date": start_date,
            "end_date": end_date,
            "daily": ",".join(DAILY_VARS),
            "timezone": "auto",
        }
        return _zip_daily(_get(FORECAST_URL, params)["daily"])

    params = {
        "latitude": lat,
        "longitude": lng,
        "start_date": start_date,
        "end_date": end_date,
        "daily": ",".join(DAILY_VARS),
        "timezone": "auto",
    }
    return _zip_daily(_get(ARCHIVE_URL, params)["daily"])


def fetch_forecast_with_history(lat, lng, date, history_days=7):
    """The forecast for `date` (which can be up to 16 days out), plus the
    `history_days` days immediately before it, as one date-sorted list of
    per-day records (each record has every field for that date, rather than
    Open-Meteo's parallel-array shape). 1 + history_days records total.

    date: "YYYY-MM-DD" string, the single day being forecast.
    Uses the forecast endpoint for the whole range rather than stitching in
    the archive API: its own recent-past data has no multi-day lag (unlike
    fetch_historical_weather's ERA5 archive), so it can serve history_days
    before `date` even when `date` itself is only a few days out.

    Raises ValueError if `date` is more than MAX_FORECAST_PAST_DAYS in the
    past - the forecast endpoint's own recent-past window doesn't go back
    that far; use fetch_historical_weather for older dates instead.
    """
    days_in_past = (to_date(today()) - to_date(date)).days
    if days_in_past > MAX_FORECAST_PAST_DAYS:
        raise ValueError(
            f"date {date!r} is {days_in_past} days in the past, beyond the forecast "
            f"endpoint's {MAX_FORECAST_PAST_DAYS}-day window; use fetch_historical_weather instead"
        )

    start_date = shift_days(date, -history_days)

    params = {
        "latitude": lat,
        "longitude": lng,
        "daily": ",".join(DAILY_VARS),
        "start_date": start_date,
        "end_date": date,
        "timezone": "auto",
    }
    return _zip_daily(_get(FORECAST_URL, params)["daily"])


def _pprint(label, data):
    print(f"\n{label}")
    print("-" * len(label))
    print(json.dumps(data, indent=2))


if __name__ == "__main__":
    # Algonquin Provincial Park, ON - sanity check against the live API.
    lat, lng = 45.5, -78.4

    _pprint("current", fetch_current_weather(lat, lng))
    _pprint("forecast", fetch_forecast(lat, lng, days=3))
    _pprint("historical", fetch_historical_weather(lat, lng, "2026-08-01", "2026-08-05"))
    _pprint("forecast_with_history", fetch_forecast_with_history(lat, lng, "2026-08-17"))
