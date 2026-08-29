import type { TrailPopularity } from '../api/trails'

export interface PopularityState {
  status: 'loading' | 'ready' | 'error'
  data: TrailPopularity | null
}

const MONTH_LABELS = ['J', 'F', 'M', 'A', 'M', 'J', 'J', 'A', 'S', 'O', 'N', 'D']
const BAR_TRACK_HEIGHT_PX = 64
// Same type-scale tiers as TrailOverview.tsx (kept local rather than a
// shared import - two files, not worth a shared module yet).
const EYEBROW = 'text-xs font-semibold uppercase tracking-wide text-(--color-neutral-content)'
const META = 'text-xs text-(--color-neutral-content)'

// research.md decision 3: a hand-rolled 12-bar chart, no charting library -
// renders correctly in its all-zero state (totalReviews === 0) per Edge
// Cases, rather than hiding or erroring.
export default function PopularityChart({ state }: { state: PopularityState }) {
  if (state.status === 'loading') {
    return <div className="h-24 animate-pulse rounded-field bg-(--color-base-300)" />
  }

  if (state.status === 'error' || !state.data) {
    return <p className={META}>Popularity data couldn't be loaded.</p>
  }

  const counts = MONTH_LABELS.map((_, i) => state.data!.byMonth[String(i + 1)] ?? 0)
  const max = Math.max(...counts, 1)
  const peakIndex = counts.indexOf(max)

  return (
    <div>
      <div className="mb-2 flex items-baseline justify-between">
        <h3 className={EYEBROW}>Popularity by month</h3>
        <span className={META}>{state.data.totalReviews} reviews</span>
      </div>
      <div className="flex h-24 items-end gap-1.5">
        {counts.map((count, i) => (
          <div key={i} className="flex flex-1 flex-col items-center gap-1" title={`${count} reviews`}>
            {/* The count is visible on hover (title) and to screen readers
                (aria-label) rather than as a permanent numeric label per
                bar, which would clutter 12 bars this narrow - the peak
                month gets its count shown outright instead. */}
            {i === peakIndex && count > 0 && (
              <span className="text-[10px] font-medium text-(--color-accent)">{count}</span>
            )}
            <div
              className="w-full rounded-t-field bg-(--color-accent)"
              // Pixels, not a CSS percentage: this div's parent is an
              // auto-height flex column (sized by its own content), and a
              // percentage height against an auto-height ancestor resolves
              // to 0 per the CSS spec - the bar was silently collapsing to
              // nothing while the labels around it rendered fine, since
              // only the bar's height depended on that percentage.
              style={{ height: `${Math.max((count / max) * BAR_TRACK_HEIGHT_PX, 2)}px` }}
              aria-label={`${count} reviews`}
            />
            <span className="text-xs text-(--color-neutral-content)">{MONTH_LABELS[i]}</span>
          </div>
        ))}
      </div>
    </div>
  )
}
