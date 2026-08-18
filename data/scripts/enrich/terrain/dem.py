import json

from curl_cffi import requests

# Ontario government ArcGIS ImageServer (Provincial DEM) - public, no key
# required. 30m native pixel resolution, confirmed via a live getSamples
# call during development.
DEM_URL = "https://ws.geoservices.lrc.gov.on.ca/arcgis5/rest/services/Elevation/Ontario_Provincial_DEM/ImageServer/getSamples"

# Comfortably under whatever the service's real limit is - 500 points in one
# request was confirmed working during development; this leaves headroom
# rather than pushing that boundary.
CHUNK_SIZE = 400


def fetch_elevations(points):
    """points: list of (lng, lat) pairs. Returns a list of elevations
    (meters, float) in the same order - one getSamples call per CHUNK_SIZE
    points, batched rather than one request per point."""
    elevations = []
    for start in range(0, len(points), CHUNK_SIZE):
        chunk = points[start:start + CHUNK_SIZE]
        geometry = {"points": chunk, "spatialReference": {"wkid": 4326}}
        params = {
            "geometry": json.dumps(geometry),
            "geometryType": "esriGeometryMultipoint",
            "returnFirstValueOnly": "true",
            "f": "json",
        }
        resp = requests.get(DEM_URL, params=params, timeout=30)
        resp.raise_for_status()
        data = resp.json()
        if "error" in data:
            raise RuntimeError(f"DEM getSamples error: {data['error']}")

        samples = data.get("samples", [])
        if len(samples) != len(chunk):
            raise RuntimeError(
                f"DEM getSamples returned {len(samples)} samples for {len(chunk)} requested points"
            )
        elevations.extend(float(s["value"]) for s in samples)

    return elevations
