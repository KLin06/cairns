from typing import Optional

from pydantic import BaseModel, ConfigDict, Field

# Response shapes mirror APP_SPEC.md's draft JSON examples directly - keep
# these two in sync as the spec evolves during implementation.


class SurfaceType(BaseModel):
    label: str
    percentOfSurface: Optional[float]


class Terrain(BaseModel):
    rockSlipRisk: Optional[str]
    soilDrainage: Optional[str]


class TrailMarker(BaseModel):
    trailId: str
    name: str
    latitude: float
    longitude: float


class TrailInfo(BaseModel):
    trailId: str
    name: Optional[str]
    difficultyRating: Optional[int]
    lengthMeters: Optional[float]
    durationMinutes: Optional[int]
    hasScrambling: bool
    surfaceTypes: list[SurfaceType]
    terrain: Terrain
    features: list[str]
    imageUrl: Optional[str]
    areaName: Optional[str]


class ConditionResult(BaseModel):
    probability: float
    predicted: bool


class ConditionsConfidence(BaseModel):
    reviewCount: int
    limitedData: bool


class ConditionsResponse(BaseModel):
    trailId: str
    date: str
    conditions: dict[str, ConditionResult]
    modelVersion: str
    confidence: ConditionsConfidence


class ActivityResponse(BaseModel):
    trailId: str
    byMonth: dict[str, int]
    byDayOfWeek: dict[str, int]
    totalReviews: int


class LineStringGeometry(BaseModel):
    type: str = "LineString"
    coordinates: list[list[float]]  # GeoJSON order: [lng, lat]


class RouteFeature(BaseModel):
    type: str = "Feature"
    geometry: LineStringGeometry
    properties: dict = {}


class RouteGeometry(BaseModel):
    type: str = "FeatureCollection"
    features: list[RouteFeature]


class DailyWeather(BaseModel):
    date: str
    tempMaxC: Optional[float]
    tempMinC: Optional[float]
    precipMm: Optional[float]
    windMaxKmh: Optional[float]
    snowCm: Optional[float]


class WeatherResponse(BaseModel):
    trailId: str
    days: list[DailyWeather]


class ValidRange(BaseModel):
    model_config = ConfigDict(populate_by_name=True)

    # "from" is a Python keyword - aliased so the wire field stays plain "from".
    from_: str = Field(alias="from")
    to: str


class WeatherErrorDetail(BaseModel):
    errorType: str  # one of: invalid_date_range, trail_unavailable, upstream_rate_limited, upstream_unavailable
    message: str
    validRange: Optional[ValidRange] = None
