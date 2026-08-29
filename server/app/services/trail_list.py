from psycopg2.extras import RealDictCursor

from app.schemas import TrailMarker
from db.connection import get_connection


def get_trail_list() -> list[TrailMarker]:
    """Every pipelined trail's map-marker identity (id/name/lat-lng) - the
    map's marker source. Reads the `trails` table (same one trail_info.py
    reads), so only trails that completed the full scrape/clean/enrich
    pipeline and landed there are ever addressable/shown as markers -
    never a live query against an external POI source (constitution
    Principle VII: OSM/AllTrails identifiers aren't reconcilable, and a
    trail outside this table has no trailId to query conditions for)."""
    conn = get_connection()
    try:
        with conn.cursor(cursor_factory=RealDictCursor) as cur:
            cur.execute("SELECT trail_id, name, latitude, longitude FROM trails ORDER BY trail_id")
            rows = cur.fetchall()
    finally:
        conn.close()

    return [
        TrailMarker(trailId=row["trail_id"], name=row["name"], latitude=row["latitude"], longitude=row["longitude"])
        for row in rows
    ]
