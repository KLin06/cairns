import json
import math
import os

from scripts.paths import DATASETS_DIR
from scripts.enrich.terrain.dem import fetch_elevations

DEM_CACHE_DIR = os.path.join(DATASETS_DIR, "dem_cache")

METERS_PER_DEGREE_LAT = 111320

# Grid spacing and neighborhood window for the local-relief calculation.
# WINDOW=1 means each point's relief is taken over its own grid cell plus
# one ring of neighbors in every direction - a ~300m-wide neighborhood at
# 100m spacing. Points closer together than the DEM's own 30m native pixel
# size wouldn't add real signal, and 100m keeps the grid (and so the number
# of DEM calls) small without smoothing away real terrain features at the
# scale a hiking trail cares about.
GRID_SPACING_M = 100
BBOX_BUFFER_M = 300
RELIEF_WINDOW = 1
LOW_RELIEF_THRESHOLD_M = 2.0


def _meters_per_degree_lng(lat):
    return METERS_PER_DEGREE_LAT * math.cos(math.radians(lat))


def _route_points(route_geometry):
    """Flatten every segment's [lat, lng] pairs into one list."""
    return [tuple(point) for segment in route_geometry["segments"] for point in segment]


def _bbox(points, buffer_m):
    lats = [lat for lat, _ in points]
    lngs = [lng for _, lng in points]
    center_lat = (min(lats) + max(lats)) / 2
    lat_buffer = buffer_m / METERS_PER_DEGREE_LAT
    lng_buffer = buffer_m / _meters_per_degree_lng(center_lat)
    return {
        "min_lat": min(lats) - lat_buffer,
        "max_lat": max(lats) + lat_buffer,
        "min_lng": min(lngs) - lng_buffer,
        "max_lng": max(lngs) + lng_buffer,
    }


def _build_grid(bbox, spacing_m):
    center_lat = (bbox["min_lat"] + bbox["max_lat"]) / 2
    lat_step = spacing_m / METERS_PER_DEGREE_LAT
    lng_step = spacing_m / _meters_per_degree_lng(center_lat)

    n_rows = math.ceil((bbox["max_lat"] - bbox["min_lat"]) / lat_step) + 1
    n_cols = math.ceil((bbox["max_lng"] - bbox["min_lng"]) / lng_step) + 1

    return {
        "min_lat": bbox["min_lat"],
        "min_lng": bbox["min_lng"],
        "lat_step": lat_step,
        "lng_step": lng_step,
        "n_rows": n_rows,
        "n_cols": n_cols,
    }


def _grid_points_lng_lat(grid):
    """(lng, lat) pairs in row-major order, matching how elevations gets
    stored/read back - Esri's getSamples takes points as [x, y] = [lng, lat]."""
    points = []
    for row in range(grid["n_rows"]):
        lat = grid["min_lat"] + row * grid["lat_step"]
        for col in range(grid["n_cols"]):
            lng = grid["min_lng"] + col * grid["lng_step"]
            points.append([lng, lat])
    return points


def _cache_path(trail_id):
    return os.path.join(DEM_CACHE_DIR, f"{trail_id}.json")


def _fetch_or_load_grid(trail_id, route_geometry):
    cache_path = _cache_path(trail_id)
    if os.path.exists(cache_path):
        with open(cache_path, "r", encoding="utf-8") as f:
            return json.load(f)

    points = _route_points(route_geometry)
    bbox = _bbox(points, BBOX_BUFFER_M)
    grid = _build_grid(bbox, GRID_SPACING_M)
    grid["elevations"] = fetch_elevations(_grid_points_lng_lat(grid))

    os.makedirs(DEM_CACHE_DIR, exist_ok=True)
    with open(cache_path, "w", encoding="utf-8") as f:
        json.dump(grid, f)

    return grid


def _nearest_index(grid, lat, lng):
    row = round((lat - grid["min_lat"]) / grid["lat_step"])
    col = round((lng - grid["min_lng"]) / grid["lng_step"])
    row = min(max(row, 0), grid["n_rows"] - 1)
    col = min(max(col, 0), grid["n_cols"] - 1)
    return row, col


def _local_relief(grid, lat, lng, window):
    center_row, center_col = _nearest_index(grid, lat, lng)
    elevations = grid["elevations"]
    n_cols = grid["n_cols"]

    neighborhood = []
    for row in range(max(center_row - window, 0), min(center_row + window, grid["n_rows"] - 1) + 1):
        for col in range(max(center_col - window, 0), min(center_col + window, n_cols - 1) + 1):
            neighborhood.append(elevations[row * n_cols + col])

    return max(neighborhood) - min(neighborhood)


def compute_percent_low_relief(trail_id, route_geometry, threshold_m=LOW_RELIEF_THRESHOLD_M, window=RELIEF_WINDOW):
    """Fraction of the route's recorded points (0-100) sitting in locally
    flat terrain (local relief under threshold_m) - a floodplain/lowland
    proxy that doesn't need any watercourse data, just the DEM. None if the
    trail has no route geometry to work from."""
    points = _route_points(route_geometry)
    if not points:
        return None

    grid = _fetch_or_load_grid(trail_id, route_geometry)
    low_relief_count = sum(
        1 for lat, lng in points if _local_relief(grid, lat, lng, window) < threshold_m
    )
    return round(100 * low_relief_count / len(points), 1)
