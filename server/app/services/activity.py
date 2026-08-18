import os

import pandas as pd
from fastapi import HTTPException

from app.config import CLEANED_REVIEWS_DIR
from app.schemas import ActivityResponse

_DAY_NAMES = ["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"]


def get_trail_activity(trail_id: str) -> ActivityResponse:
    """Historical review-date aggregation, not a prediction - see
    "Trail activity / popularity" in APP_SPEC.md for why day-of-week is a
    noisier signal than month (review post-date lags the actual hike by
    anywhere from same-day to a few weeks, which smears day-of-week but
    doesn't change what month it was)."""
    path = os.path.join(CLEANED_REVIEWS_DIR, f"{trail_id}.json")
    if not os.path.exists(path):
        raise HTTPException(status_code=404, detail=f"trail {trail_id!r} has no cleaned reviews")

    df = pd.read_json(path)
    if df.empty:
        return ActivityResponse(trailId=str(trail_id), byMonth={}, byDayOfWeek={}, totalReviews=0)

    dates = pd.to_datetime(df["date"])

    by_month = dates.dt.month.value_counts().sort_index()
    by_day = dates.dt.dayofweek.value_counts().sort_index()

    return ActivityResponse(
        trailId=str(trail_id),
        byMonth={str(month): int(count) for month, count in by_month.items()},
        byDayOfWeek={_DAY_NAMES[day]: int(count) for day, count in by_day.items()},
        totalReviews=len(df),
    )
