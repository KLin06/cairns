import json
import os

from fastapi import HTTPException

from app.config import ROUTE_GEOMETRY_DIR
from app.schemas import LineStringGeometry, RouteFeature, RouteGeometry


def get_trail_geometry(trail_id: str) -> RouteGeometry:
    path = os.path.join(ROUTE_GEOMETRY_DIR, f"{trail_id}.json")
    if not os.path.exists(path):
        raise HTTPException(
            status_code=404,
            detail=f"trail {trail_id!r} has no route geometry - has it been scraped since the geometry fetch was added?",
        )

    with open(path, "r", encoding="utf-8") as f:
        data = json.load(f)

    # Stored as [lat, lng] pairs (matches the AllTrails polyline decode);
    # GeoJSON coordinate order is [lng, lat].
    features = [
        RouteFeature(geometry=LineStringGeometry(coordinates=[[lng, lat] for lat, lng in segment]))
        for segment in (data.get("segments") or [])
    ]

    return RouteGeometry(features=features)
