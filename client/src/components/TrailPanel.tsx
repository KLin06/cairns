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
export default function TrailPanel({ onDismiss, children }: TrailPanelProps) {
  return (
    <aside
      className="absolute inset-y-4 right-4 flex w-full max-w-sm flex-col overflow-y-auto rounded-box border border-(--color-border) bg-(--color-base-100) text-(--color-base-content) shadow-lg"
      aria-label="Trail details"
    >
      <div className="flex items-center justify-between border-b border-(--color-border) p-4">
        <span className="text-sm text-(--color-neutral-content)">Trail overview</span>
        <button
          type="button"
          onClick={onDismiss}
          aria-label="Close trail details"
          className="rounded-full px-3 py-1 text-sm text-(--color-neutral-content) hover:bg-(--color-base-200)"
        >
          Close
        </button>
      </div>
      <div className="flex flex-1 flex-col gap-4 p-4">{children}</div>
    </aside>
  )
}
