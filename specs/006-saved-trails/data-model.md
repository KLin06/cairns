# Phase 1 Data Model: Saved Trails

## SavedTrailEntry (client-only, `localStorage`)

One bookmark record - matches spec.md's "Key Entities: Saved trail".

| Field     | Type   | Notes                                                                 |
|-----------|--------|------------------------------------------------------------------------|
| `trailId` | string | Same id used everywhere else client-side (`TrailMarker.trailId`, etc.) |
| `savedAt` | string | ISO 8601 timestamp, set once at save time; unchanged by later re-saves after an unsave/re-save cycle (a fresh save always gets `savedAt = now`) |

**Persistence shape**: an array of `SavedTrailEntry`, JSON-serialized under one `localStorage` key
(`cairns:savedTrails`, see contracts/saved-trails-storage.md). Not a map/object keyed by
`trailId` - an array is what both consumers (list ordering, `Set` membership check) need, and
avoids "is this JSON object malformed" ambiguity a plain object would have.

**Validation rules**:
- `trailId` must be a non-empty string; entries failing this (or any entry that isn't a
  `{trailId, savedAt}` shape) are dropped on read, not fatal - malformed `localStorage` content
  (e.g. hand-edited, or from a future/older schema version) degrades to "just skip that entry,"
  matching the same "no crash" posture as the unavailable-storage edge case.
- At most one entry per `trailId` - saving an already-saved trail is a no-op on the entry itself
  (toggle instead removes it; see below), never a duplicate row.

**State transitions** (all client-side, synchronous):
- Not saved -> Saved: append `{trailId, savedAt: new Date().toISOString()}`.
- Saved -> Not saved: remove the entry with matching `trailId`.
- Toggle is the only mutation - there is no separate "edit" operation (`savedAt` is write-once per
  save).

**Derived views** (computed in-memory from the `SavedTrailEntry[]` in `App.tsx` state, not
persisted separately):
- **List view rows**: `SavedTrailEntry[]` joined against the existing `trails: TrailMarker[]`
  (from `listTrails()`) on `trailId`, sorted by `savedAt` descending (most-recently-saved first,
  per spec.md's Ordering assumption). An entry whose `trailId` has no match in `trails` (trail
  dropped from the pipelined set) is silently excluded - Principle VII.
- **Map view pins**: the same joined/filtered list, passed to the existing `Map` component's
  `trails` prop in place of the full `trails` array.
- **Bookmark icon state** (`TrailOverview`): `isSaved = savedTrails.some(e => e.trailId === panel.overview.data.trailId)`.

## No other entities

No new server-side entity, no Postgres schema change - this feature adds exactly one client-local
persisted shape and no others (FR-015).
