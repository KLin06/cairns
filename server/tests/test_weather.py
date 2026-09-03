from datetime import date, timedelta

import psycopg2
import pytest
from fastapi.testclient import TestClient

from app.main import app
from app.services import weather as weather_module

client = TestClient(app)

TODAY = date.today()
TRAIL_ID = "99887766"


@pytest.fixture(autouse=True)
def _clear_cache():
    weather_module._CACHE.clear()
    yield
    weather_module._CACHE.clear()


@pytest.fixture
def enriched_trail(db_conn, test_database_url, monkeypatch):
    """Inserts a minimal trails row (specs/002-trail-data-storage-schema) -
    _get_trail_location now reads this table instead of
    enriched_descriptions/{trail_id}.json (specs/007-docker-containerization).
    weather_module.get_connection is repointed at the test database (same
    pattern as test_backfill.py's patched_get_connection) since db_conn
    itself uses TEST_DATABASE_URL but the HTTP request under test goes
    through weather.py's own get_connection(), which otherwise reads
    DATABASE_URL."""
    monkeypatch.setattr(weather_module, "get_connection", lambda: psycopg2.connect(test_database_url))
    with db_conn.cursor() as cur:
        cur.execute(
            "INSERT INTO trails (trail_id, name, latitude, longitude, has_scrambling) VALUES (%s, %s, %s, %s, %s)",
            (TRAIL_ID, "Test Trail", 45.85, -82.11, False),
        )
    db_conn.commit()
    return TRAIL_ID


def _fake_records(start=TODAY, count=weather_module.MAX_FORECAST_DAYS):
    """Mimics fetch_forecast's return shape: a date-sorted list of per-day dicts."""
    return [
        {
            "date": (start + timedelta(days=n)).isoformat(),
            "temperature_2m_max": 20.0 + n,
            "temperature_2m_min": 10.0 + n,
            "precipitation_sum": 1.0,
            "windspeed_10m_max": 15.0,
            "snowfall_sum": 0.0,
        }
        for n in range(count)
    ]


class _FakeHTTPError(Exception):
    def __init__(self, status_code):
        super().__init__(f"HTTP {status_code}")
        self.response = type("Resp", (), {"status_code": status_code})()


# --- User Story 1: default upcoming forecast -------------------------------


def test_default_window_returns_15_days_starting_today(enriched_trail, monkeypatch):
    monkeypatch.setattr(weather_module, "fetch_forecast", lambda lat, lng, days: _fake_records())

    resp = client.get(f"/trails/{enriched_trail}/weather")

    assert resp.status_code == 200
    body = resp.json()
    assert body["trailId"] == enriched_trail
    assert len(body["days"]) == 15
    assert body["days"][0]["date"] == TODAY.isoformat()
    assert body["days"][-1]["date"] == (TODAY + timedelta(days=14)).isoformat()


def test_unenriched_trail_returns_404_trail_unavailable(db_conn, test_database_url, monkeypatch):
    # No row inserted for this trail_id - db_conn's TRUNCATE (conftest.py)
    # guarantees a clean, empty trails table per test.
    monkeypatch.setattr(weather_module, "get_connection", lambda: psycopg2.connect(test_database_url))
    resp = client.get("/trails/00000000/weather")

    assert resp.status_code == 404
    assert resp.json()["detail"]["errorType"] == "trail_unavailable"


# --- User Story 2: specific date / date range -------------------------------


def test_single_date_returns_exactly_one_entry(enriched_trail, monkeypatch):
    monkeypatch.setattr(weather_module, "fetch_forecast", lambda lat, lng, days: _fake_records())
    target = (TODAY + timedelta(days=5)).isoformat()

    resp = client.get(f"/trails/{enriched_trail}/weather", params={"date": target})

    assert resp.status_code == 200
    days = resp.json()["days"]
    assert len(days) == 1
    assert days[0]["date"] == target


def test_date_range_returns_inclusive_set(enriched_trail, monkeypatch):
    monkeypatch.setattr(weather_module, "fetch_forecast", lambda lat, lng, days: _fake_records())
    start = TODAY + timedelta(days=2)
    end = TODAY + timedelta(days=6)

    resp = client.get(
        f"/trails/{enriched_trail}/weather",
        params={"start_date": start.isoformat(), "end_date": end.isoformat()},
    )

    assert resp.status_code == 200
    days = resp.json()["days"]
    assert len(days) == 5
    assert days[0]["date"] == start.isoformat()
    assert days[-1]["date"] == end.isoformat()


def test_date_combined_with_range_is_rejected(enriched_trail, monkeypatch):
    monkeypatch.setattr(weather_module, "fetch_forecast", lambda lat, lng, days: _fake_records())

    resp = client.get(
        f"/trails/{enriched_trail}/weather",
        params={"date": TODAY.isoformat(), "start_date": TODAY.isoformat(), "end_date": TODAY.isoformat()},
    )

    assert resp.status_code == 422
    assert resp.json()["detail"]["errorType"] == "invalid_date_range"


# --- User Story 3: rejecting out-of-range date requests ---------------------


def test_past_date_rejected_422(enriched_trail, monkeypatch):
    monkeypatch.setattr(weather_module, "fetch_forecast", lambda lat, lng, days: _fake_records())
    past = (TODAY - timedelta(days=1)).isoformat()

    resp = client.get(f"/trails/{enriched_trail}/weather", params={"date": past})

    assert resp.status_code == 422
    body = resp.json()["detail"]
    assert body["errorType"] == "invalid_date_range"


def test_date_beyond_horizon_rejected_422_with_valid_range(enriched_trail, monkeypatch):
    monkeypatch.setattr(weather_module, "fetch_forecast", lambda lat, lng, days: _fake_records())
    far_future = (TODAY + timedelta(days=weather_module.MAX_FORECAST_DAYS + 5)).isoformat()

    resp = client.get(f"/trails/{enriched_trail}/weather", params={"date": far_future})

    assert resp.status_code == 422
    body = resp.json()["detail"]
    assert body["errorType"] == "invalid_date_range"
    assert body["validRange"]["from"] == TODAY.isoformat()
    assert body["validRange"]["to"] == (TODAY + timedelta(days=weather_module.MAX_FORECAST_DAYS - 1)).isoformat()


def test_range_partially_out_of_bounds_rejected_entirely(enriched_trail, monkeypatch):
    monkeypatch.setattr(weather_module, "fetch_forecast", lambda lat, lng, days: _fake_records())
    start = TODAY
    end = TODAY + timedelta(days=weather_module.MAX_FORECAST_DAYS + 5)

    resp = client.get(
        f"/trails/{enriched_trail}/weather",
        params={"start_date": start.isoformat(), "end_date": end.isoformat()},
    )

    assert resp.status_code == 422
    assert "days" not in resp.json()


# --- User Story 4: distinguishing request errors from upstream failures -----


def test_upstream_rate_limit_exhausted_returns_503(enriched_trail, monkeypatch):
    def _raise(lat, lng, days):
        raise _FakeHTTPError(429)

    monkeypatch.setattr(weather_module, "fetch_forecast", _raise)

    resp = client.get(f"/trails/{enriched_trail}/weather")

    assert resp.status_code == 503
    assert resp.json()["detail"]["errorType"] == "upstream_rate_limited"


def test_upstream_other_failure_returns_502(enriched_trail, monkeypatch):
    def _raise(lat, lng, days):
        raise RuntimeError("boom")

    monkeypatch.setattr(weather_module, "fetch_forecast", _raise)

    resp = client.get(f"/trails/{enriched_trail}/weather")

    assert resp.status_code == 502
    assert resp.json()["detail"]["errorType"] == "upstream_unavailable"


def test_partial_upstream_response_returns_502(enriched_trail, monkeypatch):
    # Provider "succeeds" but returns fewer days than the full window - no exception raised.
    monkeypatch.setattr(weather_module, "fetch_forecast", lambda lat, lng, days: _fake_records(count=3))

    resp = client.get(f"/trails/{enriched_trail}/weather", params={"date": (TODAY + timedelta(days=10)).isoformat()})

    assert resp.status_code == 502
    assert resp.json()["detail"]["errorType"] == "upstream_unavailable"


# --- Cache behavior (spec SC-005) -------------------------------------------


def test_repeated_requests_within_window_hit_upstream_once(enriched_trail, monkeypatch):
    call_count = {"n": 0}

    def _counting_fetch(lat, lng, days):
        call_count["n"] += 1
        return _fake_records()

    monkeypatch.setattr(weather_module, "fetch_forecast", _counting_fetch)

    first = client.get(f"/trails/{enriched_trail}/weather")
    second = client.get(f"/trails/{enriched_trail}/weather", params={"date": (TODAY + timedelta(days=3)).isoformat()})

    assert first.status_code == 200
    assert second.status_code == 200
    assert call_count["n"] == 1
