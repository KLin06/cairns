import json
import os

from fastapi import HTTPException
from psycopg2.extras import RealDictCursor

from app.config import ROUTE_GEOMETRY_DIR
from app.schemas import LineStringGeometry, RouteFeature, RouteGeometry
from app.services import data_store
from db.connection import get_connection


def derive_trail_geometry(trail_id: str) -> dict | None:
    """Plain-value equivalent of get_trail_geometry(), for callers (the
    backfill script) that need the raw GeoJSON-shaped dict without
    get_trail_geometry's HTTPException/Pydantic-response shape. Returns None
    (not an exception) when the trail has no route geometry file at all -
    route geometry is legitimately optional per trail."""
    path = os.path.join(ROUTE_GEOMETRY_DIR, f"{trail_id}.json")
    if not os.path.exists(path):
        return None

    with open(path, "r", encoding="utf-8") as f:
        data = json.load(f)

    # Stored as [lat, lng] pairs (matches the AllTrails polyline decode);
    # GeoJSON coordinate order is [lng, lat].
    return {
        "type": "FeatureCollection",
        "features": [
            {
                "type": "Feature",
                "geometry": {
                    "type": "LineString",
                    "coordinates": [[lng, lat] for lat, lng in segment],
                },
                "properties": {},
            }
            for segment in (data.get("segments") or [])
        ],
    }


def get_trail_geometry(trail_id: str) -> RouteGeometry:
    """Reads the trail_geometry table (specs/002-trail-data-storage-schema),
    populated by server/db/backfill.py from the same route_geometry file
    derive_trail_geometry() above reads directly - that function stays
    file-based for the backfill script; this one is the live read-path."""
    if data_store.enabled():
        geometry = data_store.get_geometry(trail_id)
        row = {"geometry": geometry} if geometry is not None else None
    else:
        conn = get_connection()
        try:
            with conn.cursor(cursor_factory=RealDictCursor) as cur:
                cur.execute("SELECT geometry FROM trail_geometry WHERE trail_id = %s", (str(trail_id),))
                row = cur.fetchone()
        finally:
            conn.close()

    if row is None:
        raise HTTPException(
            status_code=404,
            detail=f"trail {trail_id!r} has no route geometry - has it been scraped since the geometry fetch was added?",
        )

    return RouteGeometry(
        features=[
            RouteFeature(geometry=LineStringGeometry(coordinates=f["geometry"]["coordinates"]))
            for f in row["geometry"]["features"]
        ]
    )
