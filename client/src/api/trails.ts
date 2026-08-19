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
}

export interface TrailPopularity {
  trailId: string
  byMonth: Record<string, number>
  byDayOfWeek: Record<string, number>
  totalReviews: number
}

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

// contracts/trail-list-dependency.md: the real listing endpoint doesn't
// exist yet, so this reads a local fixture behind the same shape - swapping
// in the real endpoint later is a one-line change (the fetch call below).
export async function listTrails(): Promise<TrailMarker[]> {
  const fixture = (await import('./trailListFixture.json')).default as { trails: TrailMarker[] }
  return fixture.trails
}
