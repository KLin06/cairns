from pyproj import Transformer
from shapely.geometry import LineString, Point, Polygon
from shapely.ops import transform as shapely_transform
from shapely.ops import unary_union

from scripts.enrich.terrain.client import query_bbox

# PEP_Map (same LIO ArcGIS service family as bedrock/soil) - Ontario Hydro
# Network watercourse/waterbody layers, province-wide (unlike the southern-
# Ontario-only soil survey).
WATERCOURSE_URL = "https://ws.lioservices.lrc.gov.on.ca/arcgis2/rest/services/PEP/PEP_Map/MapServer/10/query"
WATERBODY_URL = "https://ws.lioservices.lrc.gov.on.ca/arcgis2/rest/services/PEP/PEP_Map/MapServer/9/query"

# NAD83 / Ontario MNR Lambert - a metric projected CRS covering all of
# Ontario, used here so "distance" means real meters, not lat/lng degrees.
_TO_METRIC = Transformer.from_crs(4326, 3161, always_xy=True).transform

BBOX_BUFFER_DEGREES = 0.005  # ~500m - comfortably wider than any distance threshold this is used with


def _route_points(route_geometry):
    return [tuple(point) for segment in route_geometry["segments"] for point in segment]


def _bbox(points, buffer_deg):
    lats = [lat for lat, _ in points]
    lngs = [lng for _, lng in points]
    return (
        min(lats) - buffer_deg,
        min(lngs) - buffer_deg,
        max(lats) + buffer_deg,
        max(lngs) + buffer_deg,
    )


def _fetch_water_geometry(bbox):
    """Combined Shapely geometry (lines + polygons) of every watercourse and
    waterbody feature intersecting bbox, in WGS84 - None if nothing found."""
    min_lat, min_lng, max_lat, max_lng = bbox
    geoms = []

    for feature in query_bbox(WATERCOURSE_URL, min_lat, min_lng, max_lat, max_lng):
        for path in feature.get("geometry", {}).get("paths", []):
            if len(path) >= 2:
                geoms.append(LineString(path))

    for feature in query_bbox(WATERBODY_URL, min_lat, min_lng, max_lat, max_lng):
        for ring in feature.get("geometry", {}).get("rings", []):
            if len(ring) >= 3:
                geoms.append(Polygon(ring))

    return unary_union(geoms) if geoms else None


def percent_route_near_water(route_geometry, distance_threshold_m=50):
    """Percentage (0-100) of the route's recorded points within
    distance_threshold_m of any mapped watercourse or waterbody. 0.0 (not
    None) when no water is found in range - OHN_WATERCOURSE/WATERBODY are
    province-wide, so an empty result is a real "nothing nearby", not a
    coverage gap like the southern-Ontario-only soil layer."""
    points = _route_points(route_geometry)
    if not points:
        return None

    bbox = _bbox(points, BBOX_BUFFER_DEGREES)
    water = _fetch_water_geometry(bbox)
    if water is None:
        return 0.0

    water_metric = shapely_transform(_TO_METRIC, water)
    near_count = 0
    for lat, lng in points:
        x, y = _TO_METRIC(lng, lat)
        if water_metric.distance(Point(x, y)) < distance_threshold_m:
            near_count += 1

    return round(100 * near_count / len(points), 1)
