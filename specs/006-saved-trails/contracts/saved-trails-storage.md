# Contract: `localStorage` Saved-Trails Schema

This feature has no server API contract (no backend involvement, FR-015). The one interface worth
documenting is the `localStorage` persistence format, since it's the boundary between sessions/
reloads and the only place this feature's state crosses outside React.

## Key

`cairns:savedTrails`

Namespaced (`cairns:` prefix) so it doesn't collide with any other key the app or a browser
extension might set on the same origin.

## Value shape

JSON-serialized array of entries:

```json
[
  { "trailId": "abc123", "savedAt": "2026-08-29T14:03:11.482Z" },
  { "trailId": "def456", "savedAt": "2026-08-28T09:47:00.000Z" }
]
```

- `trailId`: string, matches `TrailMarker.trailId` / `TrailOverview.trailId` from `api/trails.ts`.
- `savedAt`: string, `Date.prototype.toISOString()` output (ISO 8601, UTC, millisecond precision).

An empty/never-saved state is represented by the key being absent entirely - not present as an
empty array. Both are read identically (empty list).

## Read contract (`loadSavedTrails(): SavedTrailEntry[]`)

- Missing key -> `[]`.
- Present but not valid JSON -> `[]` (parse failure caught, not thrown).
- Present, valid JSON, but not an array -> `[]`.
- Array present -> each element is validated (`typeof trailId === 'string' && trailId.length > 0`
  and `typeof savedAt === 'string'`); elements failing validation are dropped, valid elements are
  kept in their original array order (see data-model.md - callers re-sort by `savedAt` for display,
  this function does not sort).
- `localStorage.getItem` throwing (storage unavailable) -> `[]`, no exception propagates.

## Write contract (`persistSavedTrails(entries: SavedTrailEntry[]): void`)

- Serializes the full array (JSON.stringify) and calls `localStorage.setItem`.
- If `setItem` throws (quota exceeded, storage unavailable/disabled), the error is caught and
  swallowed - the caller's in-memory React state is the source of truth for the rest of that
  session regardless of whether the write succeeded (spec's documented edge case: saving still
  works for the session, just may not survive a reload).
- No partial/incremental writes - every mutation (save or unsave) writes the entire array back.
  Acceptable at this feature's scale (a personal saved-trail list, not a large dataset).

## Consumers

- `App.tsx` calls `loadSavedTrails()` exactly once, as `useState`'s lazy initializer.
- `App.tsx` calls `persistSavedTrails(nextEntries)` inside the same state update that toggles a
  trail's saved status - state and storage never drift apart within a session.
- No other module reads or writes this key directly.
