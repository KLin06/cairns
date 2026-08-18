from curl_cffi import requests


def query_point(url, lat, lng):
    """Ask which polygon(s) of an ArcGIS layer cover a given lat/lng point."""
    params = {
        "geometry": f"{lng},{lat}",
        "geometryType": "esriGeometryPoint",
        "inSR": 4326,
        "spatialRel": "esriSpatialRelIntersects",
        "outFields": "*",
        "returnGeometry": "false",
        "f": "json",
    }
    resp = requests.get(url, params=params, timeout=30)
    resp.raise_for_status()
    data = resp.json()
    if "error" in data:
        raise RuntimeError(f"ArcGIS query error for {url}: {data['error']}")
    return [feature["attributes"] for feature in data.get("features", [])]


def query_bbox(url, min_lat, min_lng, max_lat, max_lng, max_allowable_offset=0.0002):
    """Ask which features of an ArcGIS layer intersect a lat/lng bounding
    box, geometry included (unlike query_point, which only needs
    attributes) - for layers where the shape itself matters, e.g.
    distance-to-nearest-feature calculations.

    max_allowable_offset (degrees, ~0.0002 = ~20m) asks the server to
    generalize/simplify the returned geometry - without it, a bbox that
    happens to touch a Great Lake's shoreline can return a single polygon
    with tens of thousands of vertices and multi-megabyte responses that
    time out, for far more precision than a ~50m-scale proximity check
    needs."""
    params = {
        "geometry": f"{min_lng},{min_lat},{max_lng},{max_lat}",
        "geometryType": "esriGeometryEnvelope",
        "inSR": 4326,
        "outSR": 4326,
        "spatialRel": "esriSpatialRelIntersects",
        "outFields": "*",
        "returnGeometry": "true",
        "maxAllowableOffset": max_allowable_offset,
        "f": "json",
    }
    resp = requests.get(url, params=params, timeout=30)
    resp.raise_for_status()
    data = resp.json()
    if "error" in data:
        raise RuntimeError(f"ArcGIS query error for {url}: {data['error']}")
    return data.get("features", [])
