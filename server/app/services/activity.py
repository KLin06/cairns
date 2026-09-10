import os

import pandas as pd
from fastapi import HTTPException
from psycopg2.extras import RealDictCursor

from app.config import CLEANED_REVIEWS_DIR
from app.schemas import ActivityResponse
from app.services import data_store
from db.connection import get_connection

_DAY_NAMES = ["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"]


def derive_trail_activity(trail_id: str) -> dict | None:
    """Plain-value equivalent of get_trail_activity(), for callers (the
    backfill script) that need the raw aggregation without get_trail_activity's
    HTTPException/Pydantic-response shape. Returns None (not an exception)
    when the trail has no cleaned reviews file at all - a missing file means
    "not available yet", distinct from an empty reviews list, which is a
    legitimate zeroed result (see the empty-df branch below)."""
    path = os.path.join(CLEANED_REVIEWS_DIR, f"{trail_id}.json")
    if not os.path.exists(path):
        return None

    df = pd.read_json(path)
    if df.empty:
        return {"by_month": {}, "by_day_of_week": {}, "total_reviews": 0}

    dates = pd.to_datetime(df["date"])

    by_month = dates.dt.month.value_counts().sort_index()
    by_day = dates.dt.dayofweek.value_counts().sort_index()

    return {
        "by_month": {str(month): int(count) for month, count in by_month.items()},
        "by_day_of_week": {_DAY_NAMES[day]: int(count) for day, count in by_day.items()},
        "total_reviews": len(df),
    }


def get_trail_activity(trail_id: str) -> ActivityResponse:
    """Historical review-date aggregation, not a prediction - see
    "Trail activity / popularity" in APP_SPEC.md for why day-of-week is a
    noisier signal than month (review post-date lags the actual hike by
    anywhere from same-day to a few weeks, which smears day-of-week but
    doesn't change what month it was). Reads the trail_activity table
    (specs/002-trail-data-storage-schema), populated by
    server/db/backfill.py from the same cleaned_reviews file
    derive_trail_activity() above reads directly - that function stays
    file-based for the backfill script; this one is the live read-path."""
    if data_store.enabled():
        row = data_store.get_activity(trail_id)
    else:
        conn = get_connection()
        try:
            with conn.cursor(cursor_factory=RealDictCursor) as cur:
                cur.execute("SELECT * FROM trail_activity WHERE trail_id = %s", (str(trail_id),))
                row = cur.fetchone()
        finally:
            conn.close()

    if row is None:
        raise HTTPException(status_code=404, detail=f"trail {trail_id!r} has no cleaned reviews")

    return ActivityResponse(
        trailId=str(trail_id),
        byMonth=row["by_month"],
        byDayOfWeek=row["by_day_of_week"],
        totalReviews=row["total_reviews"],
    )
