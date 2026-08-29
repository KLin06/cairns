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

// Type scale for this panel - previously just text-lg (name) + text-sm
// (everything else), which gave every field the same visual weight
// regardless of role. Three deliberate tiers instead:
//   EYEBROW: section/stat labels - small, uppercase, tracked, muted
//   VALUE:   the actual data next to a label - readable, medium weight
//   META:    secondary/contextual text (units, captions) - small, muted
const EYEBROW = 'flex items-center gap-1.5 text-xs font-semibold uppercase tracking-wide text-(--color-neutral-content)'
const META = 'text-xs text-(--color-neutral-content)'

// Surface-mix row dots: a small qualitative palette (distinct hues, not
// shades of the single site accent) so the categories in this one chart
// read apart at a glance, the way a dashboard's chart legend would. A
// documented exception to design-tokens.md's "accent + neutrals only" rule -
// see the note added there. Kept as fixed dot colors on each row (see
// research/inspiration note below) rather than a stacked bar - a row-based
// list, not a bar, is the shape this redesign borrows.
const SURFACE_PALETTE = ['bg-amber-500', 'bg-emerald-500', 'bg-sky-500', 'bg-violet-500', 'bg-rose-500']

// Small inline icons for the quick-facts row and section headers - same
// hand-rolled stroke-SVG convention Sidebar.tsx already uses (no icon
// library dependency), just sized down for inline use next to text.
const ICON_PROPS = {
  width: 14,
  height: 14,
  viewBox: '0 0 24 24',
  fill: 'none',
  stroke: 'currentColor',
  strokeWidth: 2,
  strokeLinecap: 'round' as const,
  strokeLinejoin: 'round' as const,
}

function RockIcon() {
  return (
    <svg {...ICON_PROPS}>
      <path d="M3 20l6-11 4 6 3-5 5 10z" />
    </svg>
  )
}

function DropletIcon() {
  return (
    <svg {...ICON_PROPS}>
      <path d="M12 2.5s7 7.2 7 12a7 7 0 0 1-14 0c0-4.8 7-12 7-12z" />
    </svg>
  )
}

function ScrambleIcon() {
  return (
    <svg {...ICON_PROPS}>
      <path d="M4 20h4v-4h4v-4h4V8h4" />
    </svg>
  )
}

function LayersIcon() {
  return (
    <svg {...ICON_PROPS}>
      <polygon points="12 3 21 8 12 13 3 8 12 3" />
      <path d="M3 13l9 5 9-5M3 18l9 5 9-5" />
    </svg>
  )
}

function TagIcon() {
  return (
    <svg {...ICON_PROPS}>
      <path d="M20 12.5 12.5 20a1.5 1.5 0 0 1-2.1 0l-6.4-6.4a1.5 1.5 0 0 1 0-2.1L11.5 4H19a1 1 0 0 1 1 1z" />
      <circle cx="15" cy="9" r="1.3" fill="currentColor" stroke="none" />
    </svg>
  )
}

// FR-012/FR-013: name, difficulty, length, duration, surface breakdown, and
// feature chips, each with its own loading placeholder while pending.
// Layout borrows its shape from a smart-home dashboard reference (per user
// request): a large serif heading + a muted status line up top, small
// icon+label facts inline beneath it, and stadium-shaped rows for the
// surface breakdown instead of a progress bar - this app's existing
// amber-accent/slate tokens throughout, no new palette.
export default function TrailOverview({ state }: { state: OverviewState }) {
  if (state.status === 'loading') {
    return (
      <div className="flex flex-col gap-2">
        <Skeleton className="aspect-[4/3] w-full" />
        <Skeleton className="h-8 w-3/4" />
        <Skeleton className="h-4 w-1/2" />
        <Skeleton className="h-4 w-2/3" />
      </div>
    )
  }

  if (state.status === 'error' || !state.data) {
    return <p className={META}>Trail details couldn't be loaded.</p>
  }

  const {
    name,
    difficultyRating,
    lengthMeters,
    durationMinutes,
    hasScrambling,
    surfaceTypes,
    terrain,
    features,
    imageUrl,
    areaName,
  } = state.data
  const length = formatLength(lengthMeters)
  const duration = formatDuration(durationMinutes)
  const rankedSurfaces = [...surfaceTypes].sort((a, b) => (b.percentOfSurface ?? -1) - (a.percentOfSurface ?? -1))

  return (
    <div className="flex flex-col gap-3">
      {/* Sourced from enriched_descriptions' "images" array (first entry) -
          already scraped from AllTrails by the pipeline, just carried
          through to the API now. Full-bleed to the panel's edges with
          square corners (AllTrails' own trail-photo treatment) - a
          documented exception to the panel's rounded-box language, the
          same way the panel's outer viewport edge is (design-tokens.md). */}
      {imageUrl && (
        <img
          src={imageUrl}
          alt={name ? `Photo of ${name}` : 'Trail photo'}
          loading="lazy"
          className="-mx-3 -mt-3 aspect-[3/2] w-[calc(100%+1.5rem)] max-w-none object-cover"
        />
      )}

      <div>
        {/* AllTrails puts the park/area name as a small line above the
            trail name (a breadcrumb, not a caption). */}
        {areaName && <p className={`mb-0.5 ${EYEBROW}`}>{areaName}</p>}
        <h2 className="text-xl font-semibold text-(--color-base-content)">{name ?? 'Unnamed trail'}</h2>
      </div>

      {/* Muted status line under the heading - rating/length/duration
          inline and middot-separated, the same single-line density as the
          reference's "Thursday, July 09 · Partly Cloudy · 77°F outside". */}
      {(difficultyRating !== null || length || duration) && (
        <div className="flex flex-wrap items-center gap-x-2 gap-y-1">
          {difficultyRating !== null && <DifficultyStars rating={difficultyRating} />}
          {difficultyRating !== null && (length || duration) && <span className={META}>·</span>}
          {length && <span className={META}>{length}</span>}
          {length && duration && <span className={META}>·</span>}
          {duration && <span className={META}>{duration}</span>}
        </div>
      )}

      {/* Quick-facts row: small icon + label chips inline, the same shape
          as the reference's "🔒 All locked · 💡 2 lights on · 🏠 Home"
          status line - terrain facts plus the scrambling flag, all in one
          row instead of a separate bordered "Terrain" block. */}
      {(terrain.rockSlipRisk || terrain.soilDrainage || hasScrambling) && (
        <div className="flex flex-wrap items-center gap-x-3 gap-y-1.5 border-t border-(--color-border) pt-2.5">
          {terrain.rockSlipRisk && (
            <span className={`flex items-center gap-1.5 ${META}`}>
              <RockIcon />
              Rock slip: {terrain.rockSlipRisk}
            </span>
          )}
          {terrain.soilDrainage && (
            <span className={`flex items-center gap-1.5 ${META}`}>
              <DropletIcon />
              Soil: {terrain.soilDrainage}
            </span>
          )}
          {hasScrambling && (
            <span className="flex items-center gap-1.5 text-xs font-medium text-(--color-accent)">
              <ScrambleIcon />
              Scrambling
            </span>
          )}
        </div>
      )}

      {/* Surface section: stadium-shaped rows (icon dot + label + trailing
          percentage) instead of a stacked progress bar - the same "list of
          pill rows" shape as the reference's Rooms list, re-skinned with
          this app's own tokens. */}
      {rankedSurfaces.length > 0 && (
        <div className="flex flex-col gap-1.5 border-t border-(--color-border) pt-2.5">
          <h3 className={EYEBROW}>
            <LayersIcon />
            Surface
          </h3>
          <div className="flex flex-col gap-1.5">
            {rankedSurfaces.map((s, i) => (
              <div
                key={s.label}
                className="flex items-center justify-between gap-3 rounded-full bg-(--color-base-200) px-3.5 py-2"
              >
                <div className="flex items-center gap-2.5">
                  <span className={`h-2.5 w-2.5 shrink-0 rounded-full ${SURFACE_PALETTE[i % SURFACE_PALETTE.length]}`} />
                  <span className="text-sm font-medium capitalize text-(--color-base-content)">{s.label}</span>
                </div>
                {s.percentOfSurface !== null && (
                  <span className="text-sm font-semibold text-(--color-base-content)">{Math.round(s.percentOfSurface)}%</span>
                )}
              </div>
            ))}
          </div>
        </div>
      )}

      {features.length > 0 && (
        <div className="flex flex-col gap-1.5 border-t border-(--color-border) pt-2.5">
          <h3 className={EYEBROW}>
            <TagIcon />
            Features
          </h3>
          <div className="flex flex-wrap gap-2">
            {features.map((feature) => (
              <span
                key={feature}
                className="rounded-selector bg-(--color-base-200) px-3 py-1.5 text-xs font-medium text-(--color-base-content)"
              >
                {feature}
              </span>
            ))}
          </div>
        </div>
      )}
    </div>
  )
}
