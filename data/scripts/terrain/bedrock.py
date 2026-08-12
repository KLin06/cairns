from client import query_point

# Ontario government ArcGIS REST service (GeologyOntario) - public, no key required.
BEDROCK_URL = "https://ws.lioservices.lrc.gov.on.ca/arcgis2/rest/services/GeologyOntario/GeologyOntario_Map/MapServer/57/query"


def fetch_rock_type(lat, lng):
    """Bedrock Geology: rock type, formation name, geologic age/province. Province-wide."""
    return query_point(BEDROCK_URL, lat, lng)
