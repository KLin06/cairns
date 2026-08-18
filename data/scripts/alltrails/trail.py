import json
import os
import re

from scripts.paths import DATASETS_DIR
from scripts.alltrails.session import make_session, build_headers


def find_api_key(html):
    key_match = re.search(r"key%3D([A-Za-z0-9]+)%26", html) or re.search(r"[?&]key=([A-Za-z0-9]+)&", html)
    if not key_match:
        raise RuntimeError("Could not auto-discover the AllTrails API key from the trail page HTML - the page structure may have changed.")

    api_key = key_match.group(1)

    print(f"discovered API key: {api_key}")

    return api_key


def find_features(html):
    return re.findall(r'<div class="PlanYourVisit_tagName__\w+">([^<]+)</div>', html)


def populate_trail_data(session, trail_id, headers, api_key, html):
    ld_json_blocks = re.findall(r'<script type="application/ld\+json">(.*?)</script>', html)
    trail_metadata = next(
        (json.loads(block) for block in ld_json_blocks if '"@type":"LocalBusiness"' in block),
        None,
    )
    if trail_metadata is None:
        raise RuntimeError("Could not find the trail's LocalBusiness JSON-LD block on the page.")

    trail_metadata["trailId"] = trail_id
    trail_metadata["features"] = find_features(html)
    trail_metadata["surfaceTypes"] = fetch_surface_types(session, trail_id, headers, api_key)

    trail_path = os.path.join(DATASETS_DIR, "raw_descriptions", f"{trail_id}.json")
    os.makedirs(os.path.dirname(trail_path), exist_ok=True)
    with open(trail_path, "w", encoding="utf-8") as f:
        json.dump(trail_metadata, f, indent=2, ensure_ascii=False)
    print(f"saved trail info to {trail_path}")

    return trail_metadata


def save_route_geometry(session, trail_id, headers, api_key):
    route_geometry = fetch_route_geometry(session, trail_id, headers, api_key)

    geometry_path = os.path.join(DATASETS_DIR, "route_geometry", f"{trail_id}.json")
    os.makedirs(os.path.dirname(geometry_path), exist_ok=True)
    with open(geometry_path, "w", encoding="utf-8") as f:
        json.dump(route_geometry, f, indent=2, ensure_ascii=False)
    print(f"saved route geometry to {geometry_path}")

    return route_geometry


def fetch_and_save_geometry(trail_id, trail_url):
    # Standalone entry point for the "geometry" pipeline stage - visits the
    # trail page fresh (rather than reusing cached HTML) so the session has
    # the cookies AllTrails' bot-detection expects from a normal page visit
    # before the API call, same pattern as populate_trail_data.
    headers = build_headers(trail_url)
    session, html = fetch_trail_page(trail_url, headers)
    api_key = find_api_key(html)
    return save_route_geometry(session, trail_id, headers, api_key)


def fetch_surface_types(session, trail_id, headers, api_key):
    url = f"https://www.alltrails.com/api/alltrails/trails/{trail_id}/surface_types?key={api_key}"
    resp = session.get(url, headers=headers)
    resp.raise_for_status()
    return resp.json()["surfaceTypes"]["aggregation"]


def _decode_polyline(encoded, precision=5):
    # Google Encoded Polyline Algorithm Format - AllTrails serves route
    # geometry this way rather than as raw GeoJSON/coordinate arrays.
    factor = 10 ** precision
    index = 0
    length = len(encoded)
    lat = 0
    lng = 0
    coords = []

    while index < length:
        result = 0
        shift = 0
        while True:
            b = ord(encoded[index]) - 63
            index += 1
            result |= (b & 0x1f) << shift
            shift += 5
            if b < 0x20:
                break
        lat += ~(result >> 1) if result & 1 else (result >> 1)

        result = 0
        shift = 0
        while True:
            b = ord(encoded[index]) - 63
            index += 1
            result |= (b & 0x1f) << shift
            shift += 5
            if b < 0x20:
                break
        lng += ~(result >> 1) if result & 1 else (result >> 1)

        coords.append([lat / factor, lng / factor])

    return coords


def fetch_route_geometry(session, trail_id, headers, api_key):
    url = f"https://www.alltrails.com/api/alltrails/trails/{trail_id}?key={api_key}&detail=offline&include_pending=true"
    resp = session.get(url, headers=headers)
    resp.raise_for_status()
    trail_data = resp.json()["trails"][0]

    default_map = trail_data.get("defaultMap") or {}
    routes = default_map.get("routes") or []

    segments = [
        _decode_polyline(points_data)
        for route in routes
        for line_segment in (route.get("lineSegments") or [])
        if (points_data := (line_segment.get("polyline") or {}).get("pointsData"))
    ]

    return {
        "mapId": default_map.get("id"),
        "trailGeoStats": trail_data.get("trailGeoStats"),
        "segments": segments,
    }


def fetch_trail_page(trail_url, headers):
    session = make_session()

    resp = session.get(trail_url, headers=headers)
    resp.raise_for_status()

    return session, resp.text


def scrape_page(trail_id, trail_url, headers):
    session, html = fetch_trail_page(trail_url, headers)

    html_path = os.path.join(DATASETS_DIR, "html", f"{trail_id}.html")
    os.makedirs(os.path.dirname(html_path), exist_ok=True)
    with open(html_path, "w", encoding="utf-8") as f:
        f.write(html)
    print(f"saved trail page html to {html_path}")

    return session, html
