import type { ReactNode } from 'react'

interface TrailPanelProps {
  onDismiss: () => void
  children: ReactNode
}

// FR-009: full height on the first frame - no grow/expand animation. Floats
// directly over the map as its own card (not a flex sibling that pushes the
// map and leaves a flat background rectangle behind it) - rounded on every
// corner since it no longer sits flush against any viewport edge, with a
// margin gap on all sides so the map is visible all around it.
//
// No boxy header bar - the close control floats as a circular icon button
// over the photo itself (the AllTrails/map-app convention), which also lets
// the photo bleed flush to the panel's own rounded top corners instead of
// sitting below a separate chrome strip. `overflow-hidden` on the aside (not
// `overflow-y-auto`) is what clips that bleeding photo to the rounded-box
// shape - the inner content div owns the actual scrolling.
export default function TrailPanel({ onDismiss, children }: TrailPanelProps) {
  return (
    <aside
      className="absolute inset-y-4 right-4 flex w-full max-w-sm flex-col overflow-hidden rounded-box border border-(--color-border) bg-(--color-base-100) text-(--color-base-content) shadow-lg"
      aria-label="Trail details"
    >
      <button
        type="button"
        onClick={onDismiss}
        aria-label="Close trail details"
        className="absolute right-3 top-3 z-10 flex h-8 w-8 items-center justify-center rounded-full bg-black/50 text-white backdrop-blur-sm transition hover:bg-black/70"
      >
        <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.5" strokeLinecap="round">
          <path d="M6 6l12 12M18 6L6 18" />
        </svg>
      </button>
      <div className="flex flex-1 flex-col gap-3 overflow-y-auto p-3">{children}</div>
    </aside>
  )
}
