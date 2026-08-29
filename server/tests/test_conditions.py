import json
from datetime import date, timedelta

import numpy as np
import pytest
from fastapi.testclient import TestClient

from app.main import app
from app.services import conditions as conditions_module

client = TestClient(app)

TODAY = date.today()
TRAIL_ID = "99887766"

CONDITIONS = ["bugs", "flooded", "icy", "muddy", "slippery", "snow"]
FEATURES = [
    "dayOfYear",
    "antecedentPrecipIndex",
    *[f"weather_d{n}_{stub}" for n in range(8) for stub in ("tempMax", "tempMin", "rain", "snow", "windMax")],
    "trail_latitude",
    "trail_longitude",
    "trail_length",
    "trail_difficultyRating",
    "terrain_rockSlipRisk",
    "terrain_soilDrainageRank",
    "terrain_soilTextureMudPotential",
    "terrain_soilTextureGroup",
    "feature_Forests",
    "feature_Lakes",
    "trail_surface_natural_pct",
    "trail_surface_gravel_pct",
]


class _FakeModel:
    """Stands in for a fitted HistGradientBoostingClassifier - returns a
    fixed probability regardless of input, just enough to exercise the
    threshold/flag logic without needing a real fit."""

    def __init__(self, proba):
        self._proba = proba

    def predict_proba(self, X):
        return np.array([[1 - self._proba, self._proba]])


def _fake_bundle(probas=None):
    probas = probas or {c: 0.1 for c in CONDITIONS}
    return {
        "models": {f"condition_{c}": _FakeModel(probas[c]) for c in CONDITIONS},
        "thresholds": {f"condition_{c}": 0.5 for c in CONDITIONS},
        "features": FEATURES,
        "version": "2026-01-01",
    }


@pytest.fixture(autouse=True)
def _clear_cache():
    conditions_module._CACHE.clear()
    conditions_module._MODEL_BUNDLE = None
    yield
    conditions_module._CACHE.clear()
    conditions_module._MODEL_BUNDLE = None


@pytest.fixture
def enriched_trail(tmp_path, monkeypatch):
    monkeypatch.setattr(conditions_module, "ENRICHED_DESCRIPTIONS_DIR", str(tmp_path))
    (tmp_path / f"{TRAIL_ID}.json").write_text(
        json.dumps(
            {
                "latitude": 45.85,
                "longitude": -82.11,
                "length": 8368.5,
                "difficultyRating": 3,
                "features": ["Forests", "Lakes"],
                "surfaceTypes": [{"label": "natural", "percentOfSurface": 90}, {"label": "gravel", "percentOfSurface": 10}],
                "terrainData": {
                    "rock": {"rockSlipRisk": "moderate"},
                    "soil": {"drainageRank": 3, "textureMudPotential": 1, "textureGroup": "loam"},
                },
            }
        )
    )
    return TRAIL_ID


def _fake_window(start, end):
    """One record per day covering [start, end], matching
    fetch_forecast_range's return shape."""
    n_days = (end - start).days + 1
    return [
        {
            "date": (start + timedelta(days=n)).isoformat(),
            "temperature_2m_max": 20.0,
            "temperature_2m_min": 10.0,
            "rain_sum": 0.0,
            "snowfall_sum": 0.0,
            "windspeed_10m_max": 15.0,
        }
        for n in range(n_days)
    ]


def _install_fake_weather(monkeypatch):
    def _fake_fetch(lat, lng, start_date, end_date):
        return _fake_window(date.fromisoformat(start_date), date.fromisoformat(end_date))

    monkeypatch.setattr(conditions_module, "fetch_forecast_range", _fake_fetch)


def _install_fake_activity(monkeypatch, total_reviews=975):
    from app.schemas import ActivityResponse

    monkeypatch.setattr(
        conditions_module,
        "get_trail_activity",
        lambda trail_id: ActivityResponse(trailId=trail_id, byMonth={}, byDayOfWeek={}, totalReviews=total_reviews),
    )


class _FakeHTTPError(Exception):
    def __init__(self, status_code):
        super().__init__(f"HTTP {status_code}")
        self.response = type("Resp", (), {"status_code": status_code})()


# --- User Story 1: real predictions, per-condition thresholds, confidence --


def test_default_date_returns_today_with_all_six_conditions(enriched_trail, monkeypatch):
    _install_fake_weather(monkeypatch)
    _install_fake_activity(monkeypatch, total_reviews=975)
    monkeypatch.setattr(conditions_module, "_load_model_bundle", lambda: _fake_bundle())

    resp = client.get(f"/trails/{enriched_trail}/conditions")

    assert resp.status_code == 200
    body = resp.json()
    assert body["trailId"] == enriched_trail
    assert body["date"] == TODAY.isoformat()
    assert set(body["conditions"].keys()) == set(CONDITIONS)
    assert "dusty" not in body["conditions"]
    assert body["modelVersion"] == "2026-01-01"


def test_per_condition_threshold_drives_predicted_flag(enriched_trail, monkeypatch):
    _install_fake_weather(monkeypatch)
    _install_fake_activity(monkeypatch)
    bundle = _fake_bundle(probas={"bugs": 0.9, "flooded": 0.1, "icy": 0.1, "muddy": 0.6, "slippery": 0.1, "snow": 0.1})
    monkeypatch.setattr(conditions_module, "_load_model_bundle", lambda: bundle)

    resp = client.get(f"/trails/{enriched_trail}/conditions")

    body = resp.json()["conditions"]
    assert body["bugs"]["predicted"] is True
    assert body["bugs"]["probability"] == pytest.approx(0.9)
    assert body["flooded"]["predicted"] is False


def test_confidence_always_present_alongside_predictions(enriched_trail, monkeypatch):
    _install_fake_weather(monkeypatch)
    _install_fake_activity(monkeypatch, total_reviews=975)
    monkeypatch.setattr(conditions_module, "_load_model_bundle", lambda: _fake_bundle())

    resp = client.get(f"/trails/{enriched_trail}/conditions")

    confidence = resp.json()["confidence"]
    assert confidence == {"reviewCount": 975, "limitedData": False}


def test_zero_review_trail_still_renders_predictions_with_limited_data(enriched_trail, monkeypatch):
    _install_fake_weather(monkeypatch)
    _install_fake_activity(monkeypatch, total_reviews=0)
    monkeypatch.setattr(conditions_module, "_load_model_bundle", lambda: _fake_bundle())

    resp = client.get(f"/trails/{enriched_trail}/conditions")

    assert resp.status_code == 200
    assert resp.json()["confidence"] == {"reviewCount": 0, "limitedData": True}
    assert set(resp.json()["conditions"].keys()) == set(CONDITIONS)


def test_no_activity_row_treated_as_zero_reviews_not_an_error(enriched_trail, monkeypatch):
    from fastapi import HTTPException

    _install_fake_weather(monkeypatch)
    monkeypatch.setattr(conditions_module, "_load_model_bundle", lambda: _fake_bundle())

    def _raise_404(trail_id):
        raise HTTPException(status_code=404, detail="no activity")

    monkeypatch.setattr(conditions_module, "get_trail_activity", _raise_404)

    resp = client.get(f"/trails/{enriched_trail}/conditions")

    assert resp.status_code == 200
    assert resp.json()["confidence"] == {"reviewCount": 0, "limitedData": True}


# --- User Story 3: edges (date horizon, trail/upstream availability) ------


def test_unenriched_trail_returns_404_trail_unavailable(tmp_path, monkeypatch):
    monkeypatch.setattr(conditions_module, "ENRICHED_DESCRIPTIONS_DIR", str(tmp_path))

    resp = client.get("/trails/00000000/conditions")

    assert resp.status_code == 404
    assert resp.json()["detail"]["errorType"] == "trail_unavailable"


def test_trail_with_no_location_returns_404(tmp_path, monkeypatch):
    monkeypatch.setattr(conditions_module, "ENRICHED_DESCRIPTIONS_DIR", str(tmp_path))
    (tmp_path / f"{TRAIL_ID}.json").write_text(json.dumps({"latitude": None, "longitude": None}))

    resp = client.get(f"/trails/{TRAIL_ID}/conditions")

    assert resp.status_code == 404
    assert resp.json()["detail"]["errorType"] == "trail_unavailable"


def test_past_date_rejected_422(enriched_trail):
    past = (TODAY - timedelta(days=1)).isoformat()

    resp = client.get(f"/trails/{enriched_trail}/conditions", params={"date": past})

    assert resp.status_code == 422
    assert resp.json()["detail"]["errorType"] == "invalid_date_range"


def test_date_beyond_horizon_rejected_422_with_valid_range_matching_weather_endpoint(enriched_trail, monkeypatch):
    from app.services import open_meteo_client

    far_future = (TODAY + timedelta(days=open_meteo_client.MAX_FORECAST_DAYS + 5)).isoformat()

    resp = client.get(f"/trails/{enriched_trail}/conditions", params={"date": far_future})

    assert resp.status_code == 422
    body = resp.json()["detail"]
    assert body["errorType"] == "invalid_date_range"
    assert body["validRange"]["from"] == TODAY.isoformat()
    assert body["validRange"]["to"] == (TODAY + timedelta(days=open_meteo_client.MAX_FORECAST_DAYS - 1)).isoformat()


def test_upstream_rate_limit_exhausted_returns_503(enriched_trail, monkeypatch):
    def _raise(lat, lng, start_date, end_date):
        raise _FakeHTTPError(429)

    monkeypatch.setattr(conditions_module, "fetch_forecast_range", _raise)

    resp = client.get(f"/trails/{enriched_trail}/conditions")

    assert resp.status_code == 503
    assert resp.json()["detail"]["errorType"] == "upstream_rate_limited"


def test_upstream_other_failure_returns_502(enriched_trail, monkeypatch):
    def _raise(lat, lng, start_date, end_date):
        raise RuntimeError("boom")

    monkeypatch.setattr(conditions_module, "fetch_forecast_range", _raise)

    resp = client.get(f"/trails/{enriched_trail}/conditions")

    assert resp.status_code == 502
    assert resp.json()["detail"]["errorType"] == "upstream_unavailable"


def test_incomplete_upstream_window_returns_502(enriched_trail, monkeypatch):
    # Provider "succeeds" but the target date itself is missing from the window.
    monkeypatch.setattr(conditions_module, "fetch_forecast_range", lambda lat, lng, start_date, end_date: [])

    resp = client.get(f"/trails/{enriched_trail}/conditions")

    assert resp.status_code == 502
    assert resp.json()["detail"]["errorType"] == "upstream_unavailable"


# --- Cache behavior ---------------------------------------------------------


def test_repeated_requests_within_window_hit_upstream_once(enriched_trail, monkeypatch):
    call_count = {"n": 0}

    def _counting_fetch(lat, lng, start_date, end_date):
        call_count["n"] += 1
        return _fake_window(date.fromisoformat(start_date), date.fromisoformat(end_date))

    monkeypatch.setattr(conditions_module, "fetch_forecast_range", _counting_fetch)
    _install_fake_activity(monkeypatch)
    monkeypatch.setattr(conditions_module, "_load_model_bundle", lambda: _fake_bundle())

    first = client.get(f"/trails/{enriched_trail}/conditions")
    second = client.get(f"/trails/{enriched_trail}/conditions", params={"date": (TODAY + timedelta(days=3)).isoformat()})

    assert first.status_code == 200
    assert second.status_code == 200
    assert call_count["n"] == 1
