# Phase 1 Data Model: MVP Frontend Design

This is a frontend feature - "entities" here are client-side state/data shapes, not database
tables. Each traces back to spec.md's Key Entities section.

## `TrailMarker`

Sourced from the assumed trail-listing endpoint (see `contracts/trail-list-dependency.md`). One
per map marker.

| Field | Type | Notes |
|---|---|---|
| `trailId` | `string` | Matches the id used by `/trails/{id}/info`, `/activity`, `/geometry` |
| `name` | `string` | Shown in a lightweight hover label/popup before the panel opens (optional per spec, not required) |
| `latitude` | `number` | |
| `longitude` | `number` | |

## `TrailOverview`

Sourced from `GET /trails/{id}/info` (already Postgres-backed). Maps directly to that endpoint's
existing response shape (`server/app/schemas.py`'s `TrailInfo`) - no new fields invented.

| Field | Type | Notes |
|---|---|---|
| `trailId` | `string` | |
| `name` | `string \| null` | |
| `difficultyRating` | `number \| null` | |
| `lengthMeters` | `number \| null` | |
| `durationMinutes` | `number \| null` | |
| `hasScrambling` | `boolean` | Not currently displayed per spec's FR-012 field list, but present in the response - reserved for a later feature, not shown in this scope's Overview |
| `surfaceTypes` | `{label: string, percentOfSurface: number \| null}[]` | Rendered as a stacked, color-coded progress bar (largest share first) plus a legend, not a sentence - see design-tokens.md's categorical-chart exception |
| `terrain` | `{rockSlipRisk: string \| null, soilDrainage: string \| null}` | Not displayed per FR-012's field list - reserved, not this scope |
| `features` | `string[]` | Rendered as chips |

## `TrailPopularity`

Sourced from `GET /trails/{id}/activity` (already Postgres-backed). Only the monthly bucket is
used in this scope - `byDayOfWeek` exists in the response but is intentionally not rendered here
(constitution Principle VI - day-of-week popularity needs an "upcoming dates" surface to be
anchored to, which this scope doesn't have; see plan.md's Constitution Check).

| Field | Type | Notes |
|---|---|---|
| `byMonth` | `Record<'1'..'12', number>` | Drives the 12-bar chart; a trail with zero reviews still returns this key fully present with all-zero values (spec Edge Cases) |
| `totalReviews` | `number` | Not required to render per FR-012, but available if a "based on N reports" caption is added later |

## `TrailRoute`

Sourced from `GET /trails/{id}/geometry` (already Postgres-backed) - a GeoJSON `FeatureCollection`
of `LineString`s, drawn as-is via a MapLibre GeoJSON source/layer (same approach `Map.tsx` already
uses for its one hardcoded demo trail today). May be absent (404) for a trail with no route on
record - per FR-008, this is not an error state, just "no line drawn."

## `SidebarSection`

Client-only UI state, not backend data.

| Field | Type | Notes |
|---|---|---|
| `id` | `'explore' \| 'saved' \| 'favorited' \| 'plans'` | |
| `label` | `string` | |
| `enabled` | `boolean` | `true` only for `explore` (FR-002) |
| `active` | `boolean` | `true` only for `explore` in this scope (FR-003) |

## `PanelState`

Client-only UI state, held at the `App` level (or a small context) since both `Map` and
`TrailPanel` need to read/drive it.

| Field | Type | Notes |
|---|---|---|
| `selectedTrailId` | `string \| null` | `null` = panel closed; set on marker click (FR-007), cleared on dismiss (FR-010) |
| `overview` | `{status: 'loading' \| 'ready' \| 'error', data: TrailOverview \| null}` | Per-field loading state (FR-013) - each of overview/popularity/route loads independently so one slow endpoint doesn't block the others |
| `popularity` | `{status: 'loading' \| 'ready' \| 'error', data: TrailPopularity \| null}` | |
| `route` | `{status: 'loading' \| 'ready' \| 'absent' \| 'error', data: GeoJSON.FeatureCollection \| null}` | `'absent'` is the expected 404 case (FR-008), distinct from `'error'` |
| `mapViewBeforeOpen` | `{center: [number, number], zoom: number} \| null` | Captured on marker click, restored on dismiss (FR-010) - not strictly needed if the map simply never re-centers itself on selection, but captured explicitly so dismiss behavior doesn't depend on "the map just happened not to move" |

## `Theme`

Client-only, persisted.

| Field | Type | Notes |
|---|---|---|
| `mode` | `'light' \| 'dark'` | Drives the `data-theme` attribute on `<html>` (FR-019-021) |
| storage key | `"cairns-theme"` in `localStorage` | Read on app init; written on toggle |
