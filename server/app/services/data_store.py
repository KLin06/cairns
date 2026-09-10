import glob
import os

from app.config import ENRICHED_DESCRIPTIONS_DIR

# Selected via the DATA_BACKEND env var (default "postgres", unchanged
# behavior). "memory" parses the same data/datasets/ JSON files
# db/backfill.py derives Postgres rows from, and holds the result in a
# process-lifetime in-memory dict instead - no database needed at all. Chosen
# for deploy targets (Render) where the dataset is small enough (~15MB) to
# bake into the image and standing up Postgres is unwanted overhead; Postgres
# stays the default so local dev / docker-compose is unaffected.
def enabled() -> bool:
    return os.environ.get("DATA_BACKEND", "postgres").strip().lower() == "memory"


_trails: dict[str, dict] | None = None
_activity: dict[str, dict] | None = None
_geometry: dict[str, dict] | None = None


def _trail_ids() -> list[str]:
    # Same eligibility rule as db/backfill.py's list_eligible_trail_ids():
    # every trail with an enriched description file, regardless of whether
    # it also has reviews/geometry (those are optional per trail).
    return sorted(
        os.path.splitext(os.path.basename(path))[0]
        for path in glob.glob(os.path.join(ENRICHED_DESCRIPTIONS_DIR, "*.json"))
    )


def _load_all() -> None:
    global _trails, _activity, _geometry
    if _trails is not None:
        return

    # Deferred import to avoid a module-load cycle: these modules import
    # data_store (this module) at their own top level to call enabled(), so
    # importing them back at data_store's top level would cycle. By the time
    # _load_all() actually runs (first request, not import time), both sides
    # are already fully loaded and this just works.
    from app.services.activity import derive_trail_activity
    from app.services.trail_geometry import derive_trail_geometry
    from app.services.trail_info import derive_trail_record

    trails: dict[str, dict] = {}
    activity: dict[str, dict] = {}
    geometry: dict[str, dict] = {}

    for trail_id in _trail_ids():
        record = derive_trail_record(trail_id)
        if record is None:
            continue
        trails[trail_id] = record

        agg = derive_trail_activity(trail_id)
        if agg is not None:
            activity[trail_id] = agg

        geo = derive_trail_geometry(trail_id)
        if geo is not None:
            geometry[trail_id] = geo

    _trails, _activity, _geometry = trails, activity, geometry


def list_trails() -> list[dict]:
    _load_all()
    return [_trails[trail_id] for trail_id in sorted(_trails)]


def get_trail(trail_id: str) -> dict | None:
    _load_all()
    return _trails.get(str(trail_id))


def get_activity(trail_id: str) -> dict | None:
    _load_all()
    return _activity.get(str(trail_id))


def get_geometry(trail_id: str) -> dict | None:
    _load_all()
    return _geometry.get(str(trail_id))
