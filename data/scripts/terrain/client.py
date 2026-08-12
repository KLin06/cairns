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
