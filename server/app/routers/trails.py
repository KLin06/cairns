from datetime import date as date_type

from fastapi import APIRouter, Query

from app.schemas import ActivityResponse, ConditionsResponse, RouteGeometry, TrailInfo, WeatherResponse
from app.services.activity import get_trail_activity
from app.services.conditions import get_trail_conditions
from app.services.trail_geometry import get_trail_geometry
from app.services.trail_info import get_trail_info
from app.services.weather import get_trail_weather

router = APIRouter(prefix="/trails/{trail_id}", tags=["trails"])


@router.get("/info", response_model=TrailInfo)
def trail_info(trail_id: str):
    return get_trail_info(trail_id)


@router.get("/conditions", response_model=ConditionsResponse)
def trail_conditions(trail_id: str, date: date_type = Query(default_factory=date_type.today)):
    return get_trail_conditions(trail_id, date.isoformat())


@router.get("/activity", response_model=ActivityResponse)
def trail_activity(trail_id: str):
    return get_trail_activity(trail_id)


@router.get("/geometry", response_model=RouteGeometry)
def trail_geometry(trail_id: str):
    return get_trail_geometry(trail_id)


@router.get("/weather", response_model=WeatherResponse)
def trail_weather(
    trail_id: str,
    date: date_type = Query(default=None),
    start_date: date_type = Query(default=None),
    end_date: date_type = Query(default=None),
):
    return get_trail_weather(trail_id, date=date, start_date=start_date, end_date=end_date)
