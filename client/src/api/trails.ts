// Typed wrappers around the existing server/ endpoints (specs 002/003 - now
// Postgres-backed). Each per-trail function returns `null` on a 404 rather
// than throwing, matching FR-008's "absent data is not an error" convention
// (data-model.md's PanelState treats this as its own 'absent' status).

export const API_BASE = 'http://localhost:8000'

export interface TrailMarker {
  trailId: string
  name: string
  latitude: number
  longitude: number
}

export interface SurfaceType {
  label: string
  percentOfSurface: number | null
}

export interface TrailOverview {
  trailId: string
  name: string | null
  difficultyRating: number | null
  lengthMeters: number | null
  durationMinutes: number | null
  hasScrambling: boolean
  surfaceTypes: SurfaceType[]
  terrain: { rockSlipRisk: string | null; soilDrainage: string | null }
  features: string[]
  imageUrl: string | null
  areaName: string | null
}

export interface TrailPopularity {
  trailId: string
  byMonth: Record<string, number>
  byDayOfWeek: Record<string, number>
  totalReviews: number
}

export interface DailyWeather {
  date: string
  tempMaxC: number | null
  tempMinC: number | null
  precipMm: number | null
  windMaxKmh: number | null
  snowCm: number | null
}

export interface WeatherWindow {
  trailId: string
  days: DailyWeather[]
}

export interface ConditionResult {
  probability: number
  predicted: boolean
}

export interface ConditionsConfidence {
  reviewCount: number
  limitedData: boolean
}

export interface ConditionsResponse {
  trailId: string
  date: string
  conditions: Record<string, ConditionResult>
  modelVersion: string
  confidence: ConditionsConfidence
}

// US3: the caller needs to tell "outside forecast range" apart from "trail
// not in the pipeline" apart from "upstream unavailable" (FR-008), so
// conditions errors carry their errorType/message through instead of
// collapsing to null the way fetchOrNull's 404-only convention does.
export type ConditionsResult =
  | { ok: true; data: ConditionsResponse }
  | { ok: false; errorType: string; message: string; validRange?: { from: string; to: string } }

async function fetchOrNull<T>(url: string): Promise<T | null> {
  const res = await fetch(url)
  if (res.status === 404) return null
  if (!res.ok) throw new Error(`request to ${url} failed: ${res.status}`)
  return (await res.json()) as T
}

export function getTrailInfo(trailId: string): Promise<TrailOverview | null> {
  return fetchOrNull<TrailOverview>(`${API_BASE}/trails/${trailId}/info`)
}

export function getTrailActivity(trailId: string): Promise<TrailPopularity | null> {
  return fetchOrNull<TrailPopularity>(`${API_BASE}/trails/${trailId}/activity`)
}

export function getTrailGeometry(trailId: string): Promise<GeoJSON.FeatureCollection | null> {
  return fetchOrNull<GeoJSON.FeatureCollection>(`${API_BASE}/trails/${trailId}/geometry`)
}

// One call per trail selection covers the whole ~16-day window (research.md
// decision 5's frontend mirror) - the Weather section and Day Selection
// strip both read out of this same fetch rather than re-fetching per date.
export function getTrailWeatherWindow(
  trailId: string,
  startDate: string,
  endDate: string,
): Promise<WeatherWindow | null> {
  return fetchOrNull<WeatherWindow>(
    `${API_BASE}/trails/${trailId}/weather?start_date=${startDate}&end_date=${endDate}`,
  )
}

export async function getTrailConditions(trailId: string, date: string): Promise<ConditionsResult> {
  const res = await fetch(`${API_BASE}/trails/${trailId}/conditions?date=${date}`)
  if (res.ok) return { ok: true, data: (await res.json()) as ConditionsResponse }

  const body = await res.json().catch(() => null)
  const detail = body?.detail
  if (detail?.errorType) {
    return { ok: false, errorType: detail.errorType, message: detail.message, validRange: detail.validRange ?? undefined }
  }
  return { ok: false, errorType: 'unknown', message: `request failed: ${res.status}` }
}

export async function listTrails(): Promise<TrailMarker[]> {
  const res = await fetch(`${API_BASE}/trails`)
  if (!res.ok) throw new Error(`request to ${API_BASE}/trails failed: ${res.status}`)
  return (await res.json()) as TrailMarker[]
}
