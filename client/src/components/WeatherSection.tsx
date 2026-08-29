import type { ConditionResult, ConditionsResponse, DailyWeather } from '../api/trails'

export interface WeatherWindowState {
  status: 'loading' | 'ready' | 'error' | 'absent'
  days: DailyWeather[]
}

export interface ConditionsDateState {
  status: 'loading' | 'ready' | 'error'
  data: ConditionsResponse | null
  error: { errorType: string; message: string; validRange?: { from: string; to: string } } | null
}

interface WeatherSectionProps {
  selectedDate: string | null
  weatherWindow: WeatherWindowState
  conditionsByDate: Record<string, ConditionsDateState>
  onChangeDate: (date: string) => void
}

// Same type-scale tiers as TrailOverview.tsx/PopularityChart.tsx (kept
// local rather than a shared module - matches those files' own precedent).
const EYEBROW = 'text-xs font-semibold uppercase tracking-wide text-(--color-neutral-content)'
const VALUE = 'text-sm font-medium text-(--color-base-content)'
const META = 'text-xs text-(--color-neutral-content)'

// data-model.md: fixed, hardcoded condition -> gear/prep suggestion lookup
// (spec.md Assumptions - not configurable/backend-driven, six trained
// conditions is small and stable enough not to need that).
const CONDITION_LABELS: Record<string, string> = {
  bugs: 'Bugs',
  flooded: 'Flooded',
  icy: 'Icy',
  muddy: 'Muddy',
  slippery: 'Slippery',
  snow: 'Snow',
}

const PREP_SUGGESTIONS: Record<string, string> = {
  icy: 'Microspikes recommended',
  muddy: 'Waterproof boots recommended',
  bugs: 'Bring insect repellent',
  slippery: 'Trekking poles recommended',
  flooded: 'Expect stream crossings - check water levels before you go',
  snow: 'Snowshoes or traction devices recommended',
}

function Skeleton({ className }: { className: string }) {
  return <div className={`animate-pulse rounded-field bg-(--color-base-300) ${className}`} />
}

function formatDayLabel(dateStr: string): string {
  const d = new Date(`${dateStr}T00:00:00`)
  return d.toLocaleDateString(undefined, { weekday: 'short', month: 'short', day: 'numeric' })
}

function shiftDateStr(dateStr: string, n: number): string {
  const d = new Date(`${dateStr}T00:00:00`)
  d.setDate(d.getDate() + n)
  const y = d.getFullYear()
  const m = String(d.getMonth() + 1).padStart(2, '0')
  const day = String(d.getDate()).padStart(2, '0')
  return `${y}-${m}-${day}`
}

function formatTemp(c: number | null): string {
  return c === null ? '—' : `${Math.round(c)}°C`
}

// FR-010/FR-013: raw daily weather and the model's per-condition
// predictions for the selected date, together (so a flagged condition's
// "why" is checkable against the raw numbers right above it), each with
// its own independent loading state.
export default function WeatherSection({ selectedDate, weatherWindow, conditionsByDate, onChangeDate }: WeatherSectionProps) {
  if (!selectedDate) {
    return (
      <div className="flex flex-col gap-2 border-t border-(--color-border) pt-2">
        <Skeleton className="h-5 w-24" />
        <Skeleton className="h-20 w-full" />
      </div>
    )
  }

  const day = weatherWindow.days.find((d) => d.date === selectedDate) ?? null
  const conditionsState = conditionsByDate[selectedDate]
  const minDate = weatherWindow.days[0]?.date ?? selectedDate
  const maxDate = weatherWindow.days[weatherWindow.days.length - 1]?.date ?? selectedDate

  return (
    <div className="flex flex-col gap-3 border-t border-(--color-border) pt-2">
      <div className="flex items-center justify-between">
        <h3 className={EYEBROW}>Weather</h3>
        {/* FR-015: this stepper writes the same shared selectedDate the
            Day Selection strip reads/writes - Acceptance Scenario 2. */}
        <div className="flex items-center gap-1.5">
          <button
            type="button"
            aria-label="Previous day"
            disabled={selectedDate <= minDate}
            onClick={() => onChangeDate(shiftDateStr(selectedDate, -1))}
            className="flex h-6 w-6 items-center justify-center rounded-full text-(--color-base-content) disabled:opacity-30"
          >
            ‹
          </button>
          <span className={VALUE}>{formatDayLabel(selectedDate)}</span>
          <button
            type="button"
            aria-label="Next day"
            disabled={selectedDate >= maxDate}
            onClick={() => onChangeDate(shiftDateStr(selectedDate, 1))}
            className="flex h-6 w-6 items-center justify-center rounded-full text-(--color-base-content) disabled:opacity-30"
          >
            ›
          </button>
        </div>
      </div>

      {weatherWindow.status === 'loading' ? (
        <Skeleton className="h-16 w-full" />
      ) : weatherWindow.status === 'absent' ? (
        <p className={META}>Weather isn't available for this trail.</p>
      ) : weatherWindow.status === 'error' ? (
        <p className={META}>Weather is temporarily unavailable - try again shortly.</p>
      ) : day ? (
        <div className="grid grid-cols-4 gap-2 rounded-field bg-(--color-base-200) p-2">
          <Stat label="High / Low" value={`${formatTemp(day.tempMaxC)} / ${formatTemp(day.tempMinC)}`} />
          <Stat label="Precip" value={day.precipMm === null ? '—' : `${day.precipMm.toFixed(1)} mm`} />
          <Stat label="Wind" value={day.windMaxKmh === null ? '—' : `${Math.round(day.windMaxKmh)} km/h`} />
          <Stat label="Snow" value={day.snowCm === null ? '—' : `${day.snowCm.toFixed(1)} cm`} />
        </div>
      ) : (
        <p className={META}>No weather data for this day yet.</p>
      )}

      {!conditionsState || conditionsState.status === 'loading' ? (
        <Skeleton className="h-24 w-full" />
      ) : conditionsState.status === 'error' ? (
        <ConditionsError error={conditionsState.error} />
      ) : conditionsState.data ? (
        <ConditionsList data={conditionsState.data} />
      ) : null}
    </div>
  )
}

function Stat({ label, value }: { label: string; value: string }) {
  return (
    <div className="flex flex-col gap-0.5">
      <span className={META}>{label}</span>
      <span className={VALUE}>{value}</span>
    </div>
  )
}

// US3: three distinct, specific messages matching the backend's errorType
// convention (FR-008) - never a generic "something went wrong."
function ConditionsError({ error }: { error: ConditionsDateState['error'] }) {
  if (!error) return null
  if (error.errorType === 'invalid_date_range') {
    return (
      <p className={META}>
        Outside the forecast range{error.validRange ? ` (${error.validRange.from} to ${error.validRange.to})` : ''}.
      </p>
    )
  }
  if (error.errorType === 'trail_unavailable') {
    return <p className={META}>Predicted conditions aren't available for this trail.</p>
  }
  if (error.errorType === 'upstream_rate_limited' || error.errorType === 'upstream_unavailable') {
    return <p className={META}>Conditions temporarily unavailable - try again shortly.</p>
  }
  return <p className={META}>Predicted conditions couldn't be loaded.</p>
}

// FR-011/FR-012/SC-002: every flagged condition gets a prep suggestion, and
// the confidence/data-availability signal always accompanies the
// predictions - never a bare probability. Flagged conditions surface first
// (then by probability) so the ones that actually matter aren't buried
// alphabetically among five "not likely" rows.
function ConditionsList({ data }: { data: ConditionsResponse }) {
  const entries = (Object.entries(data.conditions) as [string, ConditionResult][]).sort(
    ([, a], [, b]) => Number(b.predicted) - Number(a.predicted) || b.probability - a.probability,
  )
  return (
    <div className="flex flex-col gap-2">
      <ul className="flex flex-col gap-1.5">
        {entries.map(([key, result]) => (
          <li
            key={key}
            className={`flex items-center justify-between gap-2.5 rounded-field border bg-(--color-base-200) px-2.5 py-1.5 ${
              result.predicted ? 'border-(--color-accent)' : 'border-transparent'
            }`}
          >
            <div className="flex items-center gap-2.5">
              <span
                className={`h-1.5 w-1.5 shrink-0 rounded-full ${result.predicted ? 'bg-(--color-accent)' : 'bg-(--color-base-300)'}`}
                aria-hidden="true"
              />
              <div className="flex flex-col gap-0.5">
                <span className={VALUE}>{CONDITION_LABELS[key] ?? key}</span>
                {result.predicted && PREP_SUGGESTIONS[key] && <span className={META}>{PREP_SUGGESTIONS[key]}</span>}
              </div>
            </div>
            <span className={`text-sm font-semibold ${result.predicted ? 'text-(--color-accent)' : 'text-(--color-neutral-content)'}`}>
              {Math.round(result.probability * 100)}%
            </span>
          </li>
        ))}
      </ul>
      <p className={META}>
        {data.confidence.limitedData
          ? 'Limited historical data for this trail - predictions may be less reliable.'
          : `Based on ${data.confidence.reviewCount} historical reports for this trail.`}
      </p>
    </div>
  )
}
