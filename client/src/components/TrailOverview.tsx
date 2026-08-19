import type { TrailOverview as TrailOverviewData } from '../api/trails'

export interface OverviewState {
  status: 'loading' | 'ready' | 'error'
  data: TrailOverviewData | null
}

function Skeleton({ className }: { className: string }) {
  return <div className={`animate-pulse rounded-field bg-(--color-base-300) ${className}`} />
}

const STAR_POINTS = '12 2 15 9 22 9.5 17 14.5 18.5 22 12 18 5.5 22 7 14.5 2 9.5 9 9'

// Difficulty as a 5-star bar (1-5, matching the trails table's
// difficulty_rating scale) instead of "3 / 5" text.
function DifficultyStars({ rating }: { rating: number }) {
  const filled = Math.max(0, Math.min(5, Math.round(rating)))
  return (
    <div className="flex items-center gap-0.5" role="img" aria-label={`Difficulty: ${filled} out of 5 stars`}>
      {Array.from({ length: 5 }, (_, i) => (
        <svg key={i} width="14" height="14" viewBox="0 0 24 24" strokeWidth="1.5">
          <polygon
            points={STAR_POINTS}
            style={{
              fill: i < filled ? 'var(--color-accent-hex)' : 'none',
              stroke: 'var(--color-accent-hex)',
            }}
          />
        </svg>
      ))}
    </div>
  )
}

function formatLength(meters: number | null): string | null {
  if (meters === null) return null
  return `${(meters / 1000).toFixed(1)} km`
}

function formatDuration(minutes: number | null): string | null {
  if (minutes === null) return null
  const hours = Math.floor(minutes / 60)
  const mins = minutes % 60
  return hours > 0 ? `${hours}h ${mins}m` : `${mins}m`
}

// FR-012/FR-013: name, difficulty, length, duration, surface breakdown, and
// feature chips, each with its own loading placeholder while pending.
export default function TrailOverview({ state }: { state: OverviewState }) {
  if (state.status === 'loading') {
    return (
      <div className="flex flex-col gap-3">
        <Skeleton className="h-7 w-3/4" />
        <Skeleton className="h-4 w-1/2" />
        <Skeleton className="h-4 w-2/3" />
      </div>
    )
  }

  if (state.status === 'error' || !state.data) {
    return <p className="text-sm text-(--color-neutral-content)">Trail details couldn't be loaded.</p>
  }

  const { name, difficultyRating, lengthMeters, durationMinutes, surfaceTypes, features } = state.data
  const length = formatLength(lengthMeters)
  const duration = formatDuration(durationMinutes)

  return (
    <div className="flex flex-col gap-3">
      <h2 className="text-lg font-semibold text-(--color-base-content)">{name ?? 'Unnamed trail'}</h2>

      <dl className="flex flex-wrap gap-x-4 gap-y-1 text-sm">
        {difficultyRating !== null && (
          <div>
            <dt className="text-(--color-neutral-content)">Difficulty</dt>
            <dd>
              <DifficultyStars rating={difficultyRating} />
            </dd>
          </div>
        )}
        {length && (
          <div>
            <dt className="text-(--color-neutral-content)">Length</dt>
            <dd className="text-(--color-base-content)">{length}</dd>
          </div>
        )}
        {duration && (
          <div>
            <dt className="text-(--color-neutral-content)">Duration</dt>
            <dd className="text-(--color-base-content)">{duration}</dd>
          </div>
        )}
      </dl>

      {surfaceTypes.length > 0 && (
        <div>
          <h3 className="mb-1 text-sm text-(--color-neutral-content)">Surface</h3>
          <p className="text-sm text-(--color-base-content)">
            {surfaceTypes.map((s) => `${s.label}${s.percentOfSurface !== null ? ` (${Math.round(s.percentOfSurface)}%)` : ''}`).join(', ')}
          </p>
        </div>
      )}

      {features.length > 0 && (
        <div className="flex flex-wrap gap-2">
          {features.map((feature) => (
            <span
              key={feature}
              className="rounded-selector bg-(--color-base-200) px-2.5 py-0.5 text-sm text-(--color-base-content)"
            >
              {feature}
            </span>
          ))}
        </div>
      )}
    </div>
  )
}
