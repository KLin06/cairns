import json

import psycopg2
import pytest
from psycopg2.extras import RealDictCursor

from app.services import activity as activity_module
from app.services import trail_geometry as trail_geometry_module
from app.services import trail_info as trail_info_module
from db import backfill

TRAIL_ID = "12345"

SAMPLE_REVIEWS = [
    {"date": "2026-01-05", "obstacles": [], "trailConditions": []},
    {"date": "2026-01-12", "obstacles": ["Scramble"], "trailConditions": []},
]
SAMPLE_SEGMENTS = [[[45.85, -82.11], [45.86, -82.12]]]


@pytest.fixture
def dataset_dirs(tmp_path, monkeypatch):
    """Points every service module (and backfill's own eligibility scan) at
    fake per-test dataset directories, the same pattern test_weather.py uses
    for a single directory - here across all three source directories at
    once, since backfill spans trail_info/activity/trail_geometry."""
    enriched_dir = tmp_path / "enriched_descriptions"
    reviews_dir = tmp_path / "cleaned_reviews"
    geometry_dir = tmp_path / "route_geometry"
    for d in (enriched_dir, reviews_dir, geometry_dir):
        d.mkdir()

    monkeypatch.setattr(trail_info_module, "ENRICHED_DESCRIPTIONS_DIR", str(enriched_dir))
    monkeypatch.setattr(trail_info_module, "CLEANED_REVIEWS_DIR", str(reviews_dir))
    monkeypatch.setattr(activity_module, "CLEANED_REVIEWS_DIR", str(reviews_dir))
    monkeypatch.setattr(trail_geometry_module, "ROUTE_GEOMETRY_DIR", str(geometry_dir))
    monkeypatch.setattr(backfill, "ENRICHED_DESCRIPTIONS_DIR", str(enriched_dir))

    return {"enriched": enriched_dir, "reviews": reviews_dir, "geometry": geometry_dir}


@pytest.fixture
def patched_get_connection(db_conn, test_database_url, monkeypatch):
    """For tests that go through main() / get_connection() rather than
    calling process_trail directly: points main() at the same test database
    db_conn uses, but via its own freshly-opened connection, so main()'s own
    `finally: conn.close()` doesn't tear down the connection the test itself
    still needs afterward for verification (psycopg2 connection objects
    don't allow monkeypatching individual instance attributes like close,
    and their own `.dsn` attribute redacts the password anyway)."""
    monkeypatch.setattr(backfill, "get_connection", lambda: psycopg2.connect(test_database_url))
    return db_conn


def _write_enriched(dirs, trail_id, **overrides):
    data = {
        "name": "Test Trail",
        "latitude": 45.85,
        "longitude": -82.11,
        "difficultyRating": 3,
        "length": 5000.0,
        "durationMinutes": 120,
        "terrainData": {"rock": {"rockSlipRisk": "moderate"}, "soil": {"drainage": "well-drained"}},
        "surfaceTypes": [{"label": "natural", "percentOfSurface": 99.3}],
        "features": ["waterfall"],
    }
    data.update(overrides)
    (dirs["enriched"] / f"{trail_id}.json").write_text(json.dumps(data))


def _write_reviews(dirs, trail_id, reviews):
    (dirs["reviews"] / f"{trail_id}.json").write_text(json.dumps(reviews))


def _write_geometry(dirs, trail_id, segments):
    (dirs["geometry"] / f"{trail_id}.json").write_text(json.dumps({"segments": segments}))


def _fetch(conn, table, trail_id):
    with conn.cursor(cursor_factory=RealDictCursor) as cur:
        cur.execute(f"SELECT * FROM {table} WHERE trail_id = %s", (trail_id,))
        return cur.fetchone()


# --- User Story 1: populate storage from a trail's existing pipeline output ---


def test_process_trail_writes_all_three_entities_for_fully_eligible_trail(dataset_dirs, db_conn):
    _write_enriched(dataset_dirs, TRAIL_ID)
    _write_reviews(dataset_dirs, TRAIL_ID, SAMPLE_REVIEWS)
    _write_geometry(dataset_dirs, TRAIL_ID, SAMPLE_SEGMENTS)

    outcome = backfill.process_trail(db_conn, TRAIL_ID)

    assert outcome["error"] is None
    assert not outcome["skipped"]
    assert outcome["entities_written"] == {"trails", "trail_activity", "trail_geometry"}

    trail_row = _fetch(db_conn, "trails", TRAIL_ID)
    assert trail_row["name"] == "Test Trail"
    assert trail_row["latitude"] == 45.85
    assert trail_row["longitude"] == -82.11
    assert trail_row["difficulty_rating"] == 3
    assert trail_row["has_scrambling"] is True  # 1/2 reviews mention "Scramble" >= 0.02 threshold

    activity_row = _fetch(db_conn, "trail_activity", TRAIL_ID)
    assert activity_row["total_reviews"] == 2
    assert activity_row["by_month"] == {"1": 2}

    geometry_row = _fetch(db_conn, "trail_geometry", TRAIL_ID)
    assert geometry_row["geometry"]["features"][0]["geometry"]["coordinates"] == [[-82.11, 45.85], [-82.12, 45.86]]


def test_process_trail_skips_geometry_when_absent_but_writes_the_other_two(dataset_dirs, db_conn):
    _write_enriched(dataset_dirs, TRAIL_ID)
    _write_reviews(dataset_dirs, TRAIL_ID, SAMPLE_REVIEWS)
    # no geometry file written

    outcome = backfill.process_trail(db_conn, TRAIL_ID)

    assert outcome["error"] is None
    assert outcome["entities_written"] == {"trails", "trail_activity"}
    assert _fetch(db_conn, "trails", TRAIL_ID) is not None
    assert _fetch(db_conn, "trail_activity", TRAIL_ID) is not None
    assert _fetch(db_conn, "trail_geometry", TRAIL_ID) is None


def test_process_trail_writes_overview_with_no_scrambling_when_reviews_absent_and_skips_activity(
    dataset_dirs, db_conn
):
    _write_enriched(dataset_dirs, TRAIL_ID)
    # no cleaned_reviews file written at all

    outcome = backfill.process_trail(db_conn, TRAIL_ID)

    assert outcome["error"] is None
    assert outcome["entities_written"] == {"trails"}
    trail_row = _fetch(db_conn, "trails", TRAIL_ID)
    assert trail_row["has_scrambling"] is False
    assert _fetch(db_conn, "trail_activity", TRAIL_ID) is None


# --- User Story 2: skip trails that haven't completed the pipeline ---


def test_process_trail_with_no_enriched_description_writes_nothing(dataset_dirs, db_conn):
    outcome = backfill.process_trail(db_conn, "does-not-exist")

    assert outcome["skipped"] is True
    assert outcome["entities_written"] == set()
    assert outcome["error"] is None
    assert _fetch(db_conn, "trails", "does-not-exist") is None


def test_main_with_mixed_eligible_and_ineligible_trail_ids_only_writes_eligible(
    dataset_dirs, patched_get_connection
):
    _write_enriched(dataset_dirs, TRAIL_ID)

    exit_code = backfill.main([TRAIL_ID, "not-eligible-trail"])

    assert exit_code == 0
    assert _fetch(patched_get_connection, "trails", TRAIL_ID) is not None
    assert _fetch(patched_get_connection, "trails", "not-eligible-trail") is None


def test_one_trails_failure_does_not_stop_other_trails_in_the_same_run(dataset_dirs, patched_get_connection):
    _write_enriched(dataset_dirs, "trail-a")
    _write_enriched(dataset_dirs, "trail-b")
    _write_enriched(dataset_dirs, "trail-c")
    # trail-b's enriched description is malformed JSON, so deriving it raises
    (dataset_dirs["enriched"] / "trail-b.json").write_text("{not valid json")

    exit_code = backfill.main([])  # no args -> scans list_eligible_trail_ids()

    assert exit_code == 1  # at least one trail genuinely failed
    assert _fetch(patched_get_connection, "trails", "trail-a") is not None
    assert _fetch(patched_get_connection, "trails", "trail-c") is not None
    assert _fetch(patched_get_connection, "trails", "trail-b") is None


# --- User Story 3: re-run the backfill safely ---


def test_rerun_with_unchanged_source_is_a_noop(dataset_dirs, db_conn):
    _write_enriched(dataset_dirs, TRAIL_ID)
    _write_reviews(dataset_dirs, TRAIL_ID, SAMPLE_REVIEWS)
    _write_geometry(dataset_dirs, TRAIL_ID, SAMPLE_SEGMENTS)

    backfill.process_trail(db_conn, TRAIL_ID)
    first_run = {
        table: _fetch(db_conn, table, TRAIL_ID)["updated_at"]
        for table in ("trails", "trail_activity", "trail_geometry")
    }

    second_outcome = backfill.process_trail(db_conn, TRAIL_ID)
    second_run = {
        table: _fetch(db_conn, table, TRAIL_ID)["updated_at"]
        for table in ("trails", "trail_activity", "trail_geometry")
    }

    assert second_outcome["entities_written"] == set()  # nothing changed, nothing written
    assert second_run == first_run


def test_rerun_after_description_change_updates_only_trails_row(dataset_dirs, db_conn):
    _write_enriched(dataset_dirs, TRAIL_ID)
    _write_reviews(dataset_dirs, TRAIL_ID, SAMPLE_REVIEWS)
    _write_geometry(dataset_dirs, TRAIL_ID, SAMPLE_SEGMENTS)
    backfill.process_trail(db_conn, TRAIL_ID)
    before = {
        table: _fetch(db_conn, table, TRAIL_ID)["updated_at"]
        for table in ("trails", "trail_activity", "trail_geometry")
    }

    _write_enriched(dataset_dirs, TRAIL_ID, difficultyRating=5)
    outcome = backfill.process_trail(db_conn, TRAIL_ID)

    assert outcome["entities_written"] == {"trails"}
    after_trails = _fetch(db_conn, "trails", TRAIL_ID)
    assert after_trails["difficulty_rating"] == 5
    assert after_trails["updated_at"] > before["trails"]
    assert _fetch(db_conn, "trail_activity", TRAIL_ID)["updated_at"] == before["trail_activity"]
    assert _fetch(db_conn, "trail_geometry", TRAIL_ID)["updated_at"] == before["trail_geometry"]


def test_rerun_after_reviews_change_updates_only_activity_row(dataset_dirs, db_conn):
    _write_enriched(dataset_dirs, TRAIL_ID)
    _write_reviews(dataset_dirs, TRAIL_ID, SAMPLE_REVIEWS)
    _write_geometry(dataset_dirs, TRAIL_ID, SAMPLE_SEGMENTS)
    backfill.process_trail(db_conn, TRAIL_ID)
    before = {
        table: _fetch(db_conn, table, TRAIL_ID)["updated_at"]
        for table in ("trails", "trail_activity", "trail_geometry")
    }

    _write_reviews(dataset_dirs, TRAIL_ID, SAMPLE_REVIEWS + [{"date": "2026-02-01", "obstacles": [], "trailConditions": []}])
    outcome = backfill.process_trail(db_conn, TRAIL_ID)

    assert outcome["entities_written"] == {"trail_activity"}
    after_activity = _fetch(db_conn, "trail_activity", TRAIL_ID)
    assert after_activity["total_reviews"] == 3
    assert after_activity["updated_at"] > before["trail_activity"]
    assert _fetch(db_conn, "trails", TRAIL_ID)["updated_at"] == before["trails"]
    assert _fetch(db_conn, "trail_geometry", TRAIL_ID)["updated_at"] == before["trail_geometry"]
