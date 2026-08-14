from scripts.enrich.terrain.client import query_point

# Ontario government ArcGIS REST service (LIO) - public, no key required.
SOIL_URL = "https://ws.lioservices.lrc.gov.on.ca/arcgis2/rest/services/LIO_OPEN_DATA/LIO_Open05/MapServer/9/query"


def fetch_soil_type(lat, lng):
    """Soil Survey Complex: texture, drainage, parent material, stoniness, slope. Southern Ontario only."""
    return query_point(SOIL_URL, lat, lng)
