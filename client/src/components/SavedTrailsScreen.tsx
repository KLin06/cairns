import { useMemo, useState } from 'react'
import Map from './Map'
import type { TrailMarker } from '../api/trails'
import type { SavedTrailEntry } from '../savedTrails'

type ViewMode = 'list' | 'map'

interface SavedTrailsScreenProps {
  trails: TrailMarker[]
  savedTrails: SavedTrailEntry[]
  onToggleSave: (trailId: string) => void
  onSelectTrail: (trailId: string) => void
}

const ICON_PROPS = {
  width: 16,
  height: 16,
  viewBox: '0 0 24 24',
  fill: 'none',
  stroke: 'currentColor',
  strokeWidth: 2,
  strokeLinecap: 'round' as const,
  strokeLinejoin: 'round' as const,
}

function ListIcon() {
  return (
    <svg {...ICON_PROPS}>
      <path d="M8 6h13M8 12h13M8 18h13M3 6h.01M3 12h.01M3 18h.01" />
    </svg>
  )
}

function MapIcon() {
  return (
    <svg {...ICON_PROPS}>
      <polygon points="3 6 9 3 15 6 21 3 21 18 15 21 9 18 3 21" />
      <path d="M9 3v15M15 6v15" />
    </svg>
  )
}

function BookmarkFilledIcon() {
  return (
    <svg width="18" height="18" viewBox="0 0 24 24" strokeWidth="2" stroke="currentColor">
      <path d="M19 21 12 16l-7 5V5a2 2 0 0 1 2-2h10a2 2 0 0 1 2 2z" fill="currentColor" />
    </svg>
  )
}

// Spec's Assumptions: "nothing saved yet" reads distinctly from a loading
// or error state - this screen has no async load of its own (trails/
// savedTrails are already in memory), so the only non-content state List
// view needs is this explicit empty message (FR-014). Map view instead
// falls back to the normal (pin-less) map, which already reads as empty
// on its own.
function EmptyState() {
  return (
    <div className="flex h-full flex-col items-center justify-center gap-2 px-6 text-center">
      <div className="text-(--color-neutral-content)">
        <svg width="40" height="40" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.5">
          <path d="M19 21 12 16l-7 5V5a2 2 0 0 1 2-2h10a2 2 0 0 1 2 2z" />
        </svg>
      </div>
      <p className="text-sm font-medium text-(--color-base-content)">No saved trails yet</p>
      <p className="max-w-xs text-xs text-(--color-neutral-content)">Tap the bookmark icon on any trail to add it to this list.</p>
    </div>
  )
}

// FR-007-FR-014: a dedicated screen (App.tsx swaps this in for the Explore
// map, not an overlay on top of it) offering List and Map views of the
// saved set, switched by one centered toggle. viewMode is plain local state
// - it intentionally resets to 'list' every time this component remounts,
// i.e. every time the Saved section is freshly opened (spec's Assumptions).
export default function SavedTrailsScreen({ trails, savedTrails, onToggleSave, onSelectTrail }: SavedTrailsScreenProps) {
  const [viewMode, setViewMode] = useState<ViewMode>('list')

  // Principle VII: a saved id with no match in the current pipelined
  // `trails` list (e.g. dropped from `/trails`) is silently excluded, not
  // shown as a broken row/pin. Sorted most-recently-saved first (spec's
  // Ordering assumption).
  const savedRows = useMemo(() => {
    // globalThis.Map, not the bare `Map` type: the `Map` component imported
    // above shadows the global Map identifier within this module.
    const byId = new globalThis.Map(trails.map((t) => [t.trailId, t]))
    return savedTrails
      .map((entry) => ({ entry, trail: byId.get(entry.trailId) }))
      .filter((row): row is { entry: SavedTrailEntry; trail: TrailMarker } => row.trail !== undefined)
      .sort((a, b) => b.entry.savedAt.localeCompare(a.entry.savedAt))
  }, [trails, savedTrails])

  const savedMarkers = useMemo(() => savedRows.map((row) => row.trail), [savedRows])
  const isEmpty = savedRows.length === 0

  return (
    <div className="relative h-full w-full bg-(--color-base-200)">
      {viewMode === 'list' &&
        (isEmpty ? (
          <EmptyState />
        ) : (
          <div className="mx-auto flex h-full max-w-xl flex-col gap-2 overflow-y-auto px-4 py-6 pb-24">
            {savedRows.map(({ entry, trail }) => (
              <div
                key={entry.trailId}
                role="button"
                tabIndex={0}
                onClick={() => onSelectTrail(entry.trailId)}
                onKeyDown={(e) => {
                  if (e.key === 'Enter' || e.key === ' ') onSelectTrail(entry.trailId)
                }}
                className="flex items-center justify-between gap-3 rounded-box border border-(--color-border) bg-(--color-base-100) px-4 py-3 text-left shadow-sm transition hover:border-(--color-accent)"
              >
                <span className="text-sm font-medium text-(--color-base-content)">{trail.name}</span>
                <button
                  type="button"
                  onClick={(e) => {
                    e.stopPropagation()
                    onToggleSave(entry.trailId)
                  }}
                  aria-label={`Remove ${trail.name} from saved trails`}
                  className="flex h-8 w-8 shrink-0 items-center justify-center rounded-full text-(--color-accent) transition hover:bg-(--color-base-200)"
                >
                  <BookmarkFilledIcon />
                </button>
              </div>
            ))}
          </div>
        ))}

      {/* Map view always renders the normal map, even with zero saved
          trails - an empty map with no pins already reads as "nothing
          here," unlike an empty list which would just look like a blank
          panel (that's why List view still gets its own EmptyState). */}
      {viewMode === 'map' && (
        <Map trails={savedMarkers} route={null} selectedTrailId={null} onSelectTrail={(trailId) => onSelectTrail(trailId)} />
      )}

      {/* FR-008: single toggle, horizontally centered, bottom edge (plan's
          chosen edge - comfortable thumb reach, doesn't compete with the
          top-anchored sidebar/header). */}
      <div className="pointer-events-none absolute inset-x-0 bottom-6 flex justify-center">
        <div className="pointer-events-auto flex items-center gap-1 rounded-full border border-(--color-border) bg-(--color-base-100) p-1 shadow-lg">
          {(
            [
              { mode: 'list' as const, label: 'List', icon: <ListIcon /> },
              { mode: 'map' as const, label: 'Map', icon: <MapIcon /> },
            ]
          ).map(({ mode, label, icon }) => (
            <button
              key={mode}
              type="button"
              onClick={() => setViewMode(mode)}
              aria-pressed={viewMode === mode}
              className={
                'flex items-center gap-1.5 rounded-full px-4 py-2 text-sm font-medium transition ' +
                (viewMode === mode
                  ? 'bg-(--color-accent) text-white'
                  : 'text-(--color-base-content) hover:bg-(--color-base-200)')
              }
            >
              {icon}
              {label}
            </button>
          ))}
        </div>
      </div>
    </div>
  )
}
