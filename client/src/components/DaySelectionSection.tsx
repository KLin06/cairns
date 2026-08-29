import type { TrailPopularity } from '../api/trails'
import type { ConditionsDateState, WeatherWindowState } from './WeatherSection'

interface DaySelectionSectionProps {
  selectedDate: string | null
  weatherWindow: WeatherWindowState
  conditionsByDate: Record<string, ConditionsDateState>
  popularity: TrailPopularity | null
  // The full ~16-date range this trail's window should cover (today..today+15,
  // computed once by App.tsx) - independent of whether every one of them has
  // actually resolved yet, so out-of-range/unresolved slots can still render
  // as visibly disabled instead of just not existing.
  windowDates: string[]
  onSelectDate: (date: string) => void
}

const EYEBROW = 'text-xs font-semibold uppercase tracking-wide text-(--color-neutral-content)'

const DAY_NAMES = ['Sun', 'Mon', 'Tue', 'Wed', 'Thu', 'Fri', 'Sat']

function weekdayName(dateStr: string): string {
  return DAY_NAMES[new Date(`${dateStr}T00:00:00`).getDay()]
}

function shortWeekday(dateStr: string): string {
  return new Date(`${dateStr}T00:00:00`).toLocaleDateString(undefined, { weekday: 'short' })
}

function dayNumber(dateStr: string): string {
  return String(Number(dateStr.slice(8, 10)))
}

// data-model.md's derived favorability ranking - fewest/least-severe
// flagged conditions ranks best (spec.md Assumptions: no separate model
// output, purely a client-side derived ranking for this strip's coloring).
// 0-100, higher = better (100 = nothing flagged). Rendered as a small
// fixed-hue accent bar whose *width* encodes the value (see the meter
// below) rather than painting the whole pill with a color-mix blend -
// blending this app's amber accent toward the neutral slate base in oklch
// space interpolates through the hue wheel's short way around, which
// crosses red/magenta and reads as a muddy pink, not "more/less amber."
function favorabilityPercent(state: ConditionsDateState | undefined): number | null {
  if (!state || state.status !== 'ready' || !state.data) return null
  const results = Object.values(state.data.conditions)
  if (results.length === 0) return 50
  const flagged = results.filter((c) => c.predicted).length
  return Math.round(100 - (flagged / results.length) * 100)
}

// Constitution Principle VI: day-of-week popularity only ever appears
// layered onto this strip, never as its own chart - expressed as a neutral
// dot's opacity (busier day-of-week = more opaque), relative to this
// trail's own busiest day-of-week.
function popularityRatio(popularity: TrailPopularity | null, dateStr: string): number {
  if (!popularity) return 0
  const counts = Object.values(popularity.byDayOfWeek)
  const max = Math.max(...counts, 1)
  return (popularity.byDayOfWeek[weekdayName(dateStr)] ?? 0) / max
}

// FR-014/FR-016/FR-017: one ~16-day strip serving as both the date-strip
// picker and the best-days chart - each pill colored by that day's own
// predicted-conditions favorability, with day-of-week popularity layered on
// as a busy-ness dot, never a separate chart.
export default function DaySelectionSection({
  selectedDate,
  weatherWindow,
  conditionsByDate,
  popularity,
  windowDates,
  onSelectDate,
}: DaySelectionSectionProps) {
  const availableDates = new Set(weatherWindow.status === 'ready' ? weatherWindow.days.map((d) => d.date) : [])

  return (
    <div className="flex flex-col gap-2 border-t border-(--color-border) pt-2">
      <h3 className={EYEBROW}>Best days to go</h3>
      <div className="flex gap-1.5 overflow-x-auto pb-1">
        {windowDates.map((date) => {
          // FR-018: a date the backend didn't actually resolve for this
          // trail (partial upstream response, or genuinely beyond the
          // horizon) is rendered disabled, never silently tappable.
          const disabled = !availableDates.has(date)
          const isSelected = date === selectedDate
          const favorability = favorabilityPercent(conditionsByDate[date])
          const popRatio = popularityRatio(popularity, date)

          return (
            <button
              key={date}
              type="button"
              disabled={disabled}
              onClick={() => onSelectDate(date)}
              aria-label={`${shortWeekday(date)} ${dayNumber(date)}${disabled ? ' (unavailable)' : ''}`}
              aria-pressed={isSelected}
              className={`flex shrink-0 flex-col items-center gap-1.5 rounded-field border px-2.5 py-2 text-center transition disabled:cursor-not-allowed disabled:opacity-30 ${
                isSelected
                  ? 'border-(--color-accent) bg-(--color-accent) text-(--color-accent-content)'
                  : 'border-(--color-border) bg-(--color-base-200) text-(--color-base-content)'
              }`}
            >
              <span className={`text-[10px] font-medium ${isSelected ? 'text-(--color-accent-content)' : 'text-(--color-neutral-content)'}`}>
                {shortWeekday(date)}
              </span>
              <span className="text-xs font-semibold">{dayNumber(date)}</span>
              {/* Favorability meter: a fixed-hue accent bar whose width
                  encodes the ranking - never a blended/tinted background
                  (see favorabilityPercent's comment). */}
              <span
                className={`h-1 w-6 overflow-hidden rounded-full ${isSelected ? 'bg-(--color-accent-content)/25' : 'bg-(--color-base-300)'}`}
                aria-hidden="true"
              >
                <span
                  className={`block h-full rounded-full ${isSelected ? 'bg-(--color-accent-content)' : 'bg-(--color-accent)'}`}
                  style={{ width: `${favorability ?? 0}%` }}
                />
              </span>
              {/* Day-of-week popularity, layered on the same pill (constitution Principle VI). */}
              <span
                className={`h-1 w-1 rounded-full ${isSelected ? 'bg-(--color-accent-content)' : 'bg-(--color-neutral-content)'}`}
                style={{ opacity: disabled ? 0 : 0.3 + popRatio * 0.7 }}
                aria-hidden="true"
              />
            </button>
          )
        })}
      </div>
    </div>
  )
}
