// localStorage persistence for the saved-trails bookmark set - see
// specs/006-saved-trails/contracts/saved-trails-storage.md for the full
// read/write contract this module implements.

const STORAGE_KEY = 'cairns:savedTrails'

export interface SavedTrailEntry {
  trailId: string
  savedAt: string
}

function isValidEntry(value: unknown): value is SavedTrailEntry {
  if (typeof value !== 'object' || value === null) return false
  const entry = value as Record<string, unknown>
  return typeof entry.trailId === 'string' && entry.trailId.length > 0 && typeof entry.savedAt === 'string'
}

// Never throws - a missing key, invalid JSON, non-array value, malformed
// entries, or localStorage being unavailable entirely (private browsing)
// all resolve to an empty list rather than an error (spec's documented
// edge case).
export function loadSavedTrails(): SavedTrailEntry[] {
  try {
    const raw = localStorage.getItem(STORAGE_KEY)
    if (!raw) return []
    const parsed = JSON.parse(raw)
    if (!Array.isArray(parsed)) return []
    return parsed.filter(isValidEntry)
  } catch {
    return []
  }
}

// Never throws - a write failure (quota exceeded, storage disabled) is
// swallowed; the caller's in-memory state remains the source of truth for
// the rest of that session regardless of whether this succeeded.
export function persistSavedTrails(entries: SavedTrailEntry[]): void {
  try {
    localStorage.setItem(STORAGE_KEY, JSON.stringify(entries))
  } catch {
    // ignore - see contract note above
  }
}
