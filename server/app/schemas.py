from typing import Optional

from pydantic import BaseModel

# Response shapes mirror APP_SPEC.md's draft JSON examples directly - keep
# these two in sync as the spec evolves during implementation.


class SurfaceType(BaseModel):
    label: str
    percentOfSurface: Optional[float]


class Terrain(BaseModel):
    rockSlipRisk: Optional[str]
    soilDrainage: Optional[str]


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


class ConditionResult(BaseModel):
    probability: float
    predicted: bool


class ConditionsResponse(BaseModel):
    trailId: str
    date: str
    conditions: dict[str, ConditionResult]
    modelVersion: str


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
