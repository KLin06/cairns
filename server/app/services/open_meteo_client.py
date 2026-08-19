import random
import time

from curl_cffi import requests

FORECAST_URL = "https://api.open-meteo.com/v1/forecast"

MAX_FORECAST_DAYS = 16  # Open-Meteo forecast endpoint's forecast_days cap - confirmed live:
# days=16 returns today..today+15 (16 days total), days=17 is rejected with 400.

# Mirrors the retry/backoff behavior in data/scripts/enrich/weather/open_meteo.py
# (duplicated deliberately, not imported - server/ has no runtime dependency on
# data/scripts, so it keeps working standalone). Keep both in sync if
# Open-Meteo's rate-limit behavior changes.
MAX_RETRIES = 5
RETRY_BASE_DELAY = 2.0

DAILY_VARS = [
    "temperature_2m_max",
    "temperature_2m_min",
    "precipitation_sum",
    "rain_sum",
    "snowfall_sum",
    "windspeed_10m_max",
]


def _get(url, params):
    for attempt in range(MAX_RETRIES):
        resp = requests.get(url, params=params, timeout=30)
        if resp.status_code == 429 and attempt < MAX_RETRIES - 1:
            wait = RETRY_BASE_DELAY * (2**attempt) + random.uniform(0, 1)
            time.sleep(wait)
            continue
        resp.raise_for_status()
        return resp.json()


def _zip_daily(daily):
    """Turn Open-Meteo's columnar {var: [v1, v2, ...], time: [d1, d2, ...]}
    shape into one dict per date: [{"date": d1, var: v1, ...}, ...]."""
    dates = daily["time"]
    fields = {k: v for k, v in daily.items() if k != "time"}
    return [{"date": date, **{field: values[i] for field, values in fields.items()}} for i, date in enumerate(dates)]


def fetch_forecast(lat, lng, days=7):
    """Daily forecast (up to MAX_FORECAST_DAYS days out) at a point, as a
    date-sorted list of per-day records."""
    params = {
        "latitude": lat,
        "longitude": lng,
        "daily": ",".join(DAILY_VARS),
        "forecast_days": days,
        "timezone": "auto",
    }
    return _zip_daily(_get(FORECAST_URL, params)["daily"])
