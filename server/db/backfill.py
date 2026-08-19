import argparse
import os
import sys

from psycopg2.extras import Json, RealDictCursor

from app.config import ENRICHED_DESCRIPTIONS_DIR
from app.services.activity import derive_trail_activity
from app.services.trail_geometry import derive_trail_geometry
from app.services.trail_info import derive_trail_record
from db.connection import get_connection

TRAIL_COLUMNS = [
    "name",
    "latitude",
    "longitude",
    "difficulty_rating",
    "length_meters",
    "duration_minutes",
    "has_scrambling",
    "rock_slip_risk",
    "soil_drainage",
    "surface_types",
    "features",
]
ACTIVITY_COLUMNS = ["by_month", "by_day_of_week", "total_reviews"]


def list_eligible_trail_ids() -> list[str]:
    return sorted(
        os.path.splitext(name)[0] for name in os.listdir(ENRICHED_DESCRIPTIONS_DIR) if name.endswith(".json")
    )


def _existing_row(conn, table, trail_id):
    with conn.cursor(cursor_factory=RealDictCursor) as cur:
        cur.execute(f"SELECT * FROM {table} WHERE trail_id = %s", (trail_id,))
        return cur.fetchone()


def upsert_trail(conn, record: dict) -> bool:
    existing = _existing_row(conn, "trails", record["trail_id"])
    if existing is not None and all(existing[c] == record[c] for c in TRAIL_COLUMNS):
        return False

    with conn.cursor() as cur:
        cur.execute(
            """
            INSERT INTO trails (
                trail_id, name, latitude, longitude, difficulty_rating,
                length_meters, duration_minutes, has_scrambling,
                rock_slip_risk, soil_drainage, surface_types, features, updated_at
            ) VALUES (
                %(trail_id)s, %(name)s, %(latitude)s, %(longitude)s, %(difficulty_rating)s,
                %(length_meters)s, %(duration_minutes)s, %(has_scrambling)s,
                %(rock_slip_risk)s, %(soil_drainage)s, %(surface_types)s, %(features)s, now()
            )
            ON CONFLICT (trail_id) DO UPDATE SET
                name = EXCLUDED.name,
                latitude = EXCLUDED.latitude,
                longitude = EXCLUDED.longitude,
                difficulty_rating = EXCLUDED.difficulty_rating,
                length_meters = EXCLUDED.length_meters,
                duration_minutes = EXCLUDED.duration_minutes,
                has_scrambling = EXCLUDED.has_scrambling,
                rock_slip_risk = EXCLUDED.rock_slip_risk,
                soil_drainage = EXCLUDED.soil_drainage,
                surface_types = EXCLUDED.surface_types,
                features = EXCLUDED.features,
                updated_at = now()
            """,
            {
                **record,
                "surface_types": Json(record["surface_types"]) if record["surface_types"] is not None else None,
                "features": Json(record["features"]) if record["features"] is not None else None,
            },
        )
    conn.commit()
    return True


def upsert_trail_activity(conn, trail_id: str, agg: dict) -> bool:
    existing = _existing_row(conn, "trail_activity", trail_id)
    if existing is not None and all(existing[c] == agg[c] for c in ACTIVITY_COLUMNS):
        return False

    with conn.cursor() as cur:
        cur.execute(
            """
            INSERT INTO trail_activity (trail_id, by_month, by_day_of_week, total_reviews, updated_at)
            VALUES (%(trail_id)s, %(by_month)s, %(by_day_of_week)s, %(total_reviews)s, now())
            ON CONFLICT (trail_id) DO UPDATE SET
                by_month = EXCLUDED.by_month,
                by_day_of_week = EXCLUDED.by_day_of_week,
                total_reviews = EXCLUDED.total_reviews,
                updated_at = now()
            """,
            {
                "trail_id": trail_id,
                "by_month": Json(agg["by_month"]),
                "by_day_of_week": Json(agg["by_day_of_week"]),
                "total_reviews": agg["total_reviews"],
            },
        )
    conn.commit()
    return True


def upsert_trail_geometry(conn, trail_id: str, geometry: dict) -> bool:
    existing = _existing_row(conn, "trail_geometry", trail_id)
    if existing is not None and existing["geometry"] == geometry:
        return False

    with conn.cursor() as cur:
        cur.execute(
            """
            INSERT INTO trail_geometry (trail_id, geometry, updated_at)
            VALUES (%(trail_id)s, %(geometry)s, now())
            ON CONFLICT (trail_id) DO UPDATE SET
                geometry = EXCLUDED.geometry,
                updated_at = now()
            """,
            {"trail_id": trail_id, "geometry": Json(geometry)},
        )
    conn.commit()
    return True


def process_trail(conn, trail_id: str) -> dict:
    """Derives and upserts all three entities for one trail. Never raises -
    a trail with no enriched description is reported as skipped (FR-001),
    and any exception while deriving or upserting a single entity is caught
    and recorded in "error" rather than propagated, so one trail's failure
    (or one entity's failure within a trail) can never stop the rest of a
    batch (FR-008)."""
    outcome = {"trail_id": trail_id, "entities_written": set(), "error": None, "skipped": False}
    errors = []

    try:
        record = derive_trail_record(trail_id)
    except Exception as exc:  # noqa: BLE001 - isolate this trail's failure, don't propagate
        outcome["error"] = f"trails: {exc}"
        return outcome

    if record is None:
        outcome["skipped"] = True
        return outcome

    try:
        if upsert_trail(conn, record):
            outcome["entities_written"].add("trails")
    except Exception as exc:  # noqa: BLE001
        errors.append(f"trails: {exc}")

    try:
        agg = derive_trail_activity(trail_id)
        if agg is not None and upsert_trail_activity(conn, trail_id, agg):
            outcome["entities_written"].add("trail_activity")
    except Exception as exc:  # noqa: BLE001
        errors.append(f"trail_activity: {exc}")

    try:
        geometry = derive_trail_geometry(trail_id)
        if geometry is not None and upsert_trail_geometry(conn, trail_id, geometry):
            outcome["entities_written"].add("trail_geometry")
    except Exception as exc:  # noqa: BLE001
        errors.append(f"trail_geometry: {exc}")

    if errors:
        outcome["error"] = "; ".join(errors)
    return outcome


def _report(outcomes: list[dict]) -> int:
    succeeded = skipped = failed = 0
    for outcome in outcomes:
        if outcome["skipped"]:
            skipped += 1
            print(f"{outcome['trail_id']}: skipped (not eligible - no enriched description)")
        elif outcome["error"]:
            failed += 1
            print(f"{outcome['trail_id']}: FAILED - {outcome['error']}")
        else:
            succeeded += 1
            entities = ", ".join(sorted(outcome["entities_written"])) or "no changes"
            print(f"{outcome['trail_id']}: ok ({entities})")

    print(f"\n{len(outcomes)} attempted, {succeeded} succeeded, {skipped} skipped, {failed} failed")
    return 1 if failed else 0


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(
        description="Backfill trails/trail_activity/trail_geometry from data/datasets/ pipeline output."
    )
    parser.add_argument(
        "trail_ids",
        nargs="*",
        help="Specific trail ids to process; omit to process every eligible trail under enriched_descriptions/",
    )
    args = parser.parse_args(argv)

    trail_ids = args.trail_ids or list_eligible_trail_ids()

    conn = get_connection()
    try:
        # Every trail_id is always attempted, regardless of earlier failures -
        # process_trail never raises, so nothing here can short-circuit the loop.
        outcomes = [process_trail(conn, trail_id) for trail_id in trail_ids]
    finally:
        conn.close()

    return _report(outcomes)


if __name__ == "__main__":
    sys.exit(main())
