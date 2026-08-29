import { useEffect, useRef, useState } from 'react'
import Map, { type MapHandle, type MapView } from './components/Map'
import Sidebar from './components/Sidebar'
import TrailPanel from './components/TrailPanel'
import TrailOverview, { type OverviewState } from './components/TrailOverview'
import PopularityChart, { type PopularityState } from './components/PopularityChart'
import WeatherSection, { type ConditionsDateState, type WeatherWindowState } from './components/WeatherSection'
import DaySelectionSection from './components/DaySelectionSection'
import {
  getTrailActivity,
  getTrailConditions,
  getTrailGeometry,
  getTrailInfo,
  getTrailWeatherWindow,
  listTrails,
  type TrailMarker,
} from './api/trails'

interface RouteState {
  status: 'loading' | 'ready' | 'absent' | 'error'
  data: GeoJSON.FeatureCollection | null
}

// Must match server/app/services/open_meteo_client.py's MAX_FORECAST_DAYS -
// the client requests exactly the window the backend can actually serve
// (constitution Principle III).
const FORECAST_WINDOW_DAYS = 16

function isoDate(d: Date): string {
  const y = d.getFullYear()
  const m = String(d.getMonth() + 1).padStart(2, '0')
  const day = String(d.getDate()).padStart(2, '0')
  return `${y}-${m}-${day}`
}

function addDays(d: Date, n: number): Date {
  const copy = new Date(d)
  copy.setDate(copy.getDate() + n)
  return copy
}

// data-model.md's PanelState, held here since Map/TrailPanel/WeatherSection/
// DaySelectionSection all read/drive pieces of it - selectedDate in
// particular is the single shared state constitution Principle IV requires.
interface PanelState {
  selectedTrailId: string | null
  overview: OverviewState
  popularity: PopularityState
  route: RouteState
  mapViewBeforeOpen: MapView | null
  selectedDate: string | null
  weatherWindow: WeatherWindowState
  conditionsByDate: Record<string, ConditionsDateState>
}

const EMPTY_PANEL: PanelState = {
  selectedTrailId: null,
  overview: { status: 'loading', data: null },
  popularity: { status: 'loading', data: null },
  route: { status: 'loading', data: null },
  mapViewBeforeOpen: null,
  selectedDate: null,
  weatherWindow: { status: 'loading', days: [] },
  conditionsByDate: {},
}

function App() {
  const mapHandleRef = useRef<MapHandle>(null)
  const [trails, setTrails] = useState<TrailMarker[]>([])
  const [panel, setPanel] = useState<PanelState>(EMPTY_PANEL)
  // Dedupes in-flight/completed conditions requests per (trailId, date) -
  // requestConditions is called both for the selected date (Weather
  // section) and, once Day Selection mounts, for every date in the window,
  // so without this a rapid sequence of calls for the same date would fire
  // the fetch more than once. Keyed by trailId too so a stale key from a
  // previous trail selection can't suppress a legitimate re-fetch.
  const requestedConditionsRef = useRef<Set<string>>(new Set())

  useEffect(() => {
    listTrails().then(setTrails).catch(console.error)
  }, [])

  // FR-020: keyed per (trailId, date) rather than a single "current
  // conditions" slot, so a stale response for a since-abandoned date can
  // only ever write into its own date's entry - it can never overwrite
  // whatever date is currently selected and displayed.
  function requestConditions(trailId: string, date: string) {
    const key = `${trailId}:${date}`
    if (requestedConditionsRef.current.has(key)) return
    requestedConditionsRef.current.add(key)

    setPanel((prev) =>
      prev.selectedTrailId === trailId
        ? { ...prev, conditionsByDate: { ...prev.conditionsByDate, [date]: { status: 'loading', data: null, error: null } } }
        : prev,
    )

    getTrailConditions(trailId, date).then((result) => {
      setPanel((prev) => {
        if (prev.selectedTrailId !== trailId) return prev
        const entry: ConditionsDateState = result.ok
          ? { status: 'ready', data: result.data, error: null }
          : { status: 'error', data: null, error: { errorType: result.errorType, message: result.message, validRange: result.validRange } }
        return { ...prev, conditionsByDate: { ...prev.conditionsByDate, [date]: entry } }
      })
    })
  }

  // Principle IV: the single setter every date-aware surface (Weather
  // section's stepper, Day Selection's strip) calls - whichever one the
  // user interacts with, the other stays in sync because they all read the
  // same panel.selectedDate.
  function setSelectedDate(date: string) {
    if (!panel.selectedTrailId) return
    setPanel((prev) => (prev.selectedTrailId ? { ...prev, selectedDate: date } : prev))
    requestConditions(panel.selectedTrailId, date)
  }

  // FR-007: clicking a marker (first time, or while a panel is already
  // open for a different trail) sets/updates this same panel state, never
  // unmounts/remounts TrailPanel.
  function handleSelectTrail(trailId: string, viewBeforeSelect: MapView) {
    requestedConditionsRef.current = new Set()
    setPanel((prev) => ({
      selectedTrailId: trailId,
      overview: { status: 'loading', data: null },
      popularity: { status: 'loading', data: null },
      route: { status: 'loading', data: null },
      // Only capture the view once - if a second marker is clicked while a
      // panel is already open, dismiss should still restore the view from
      // *before the first* selection, not the intermediate one.
      mapViewBeforeOpen: prev.mapViewBeforeOpen ?? viewBeforeSelect,
      selectedDate: null,
      weatherWindow: { status: 'loading', days: [] },
      conditionsByDate: {},
    }))

    const today = new Date()
    const todayIso = isoDate(today)
    const horizonEndIso = isoDate(addDays(today, FORECAST_WINDOW_DAYS - 1))

    // FR-009/FR-010: one weather-window fetch per trail selection (not per
    // date) - the Weather section and Day Selection strip both read the
    // selected/each date's entry out of this same window locally.
    getTrailWeatherWindow(trailId, todayIso, horizonEndIso)
      .then((data) => {
        setPanel((prev) =>
          prev.selectedTrailId === trailId
            ? {
                ...prev,
                weatherWindow: { status: data ? 'ready' : 'absent', days: data?.days ?? [] },
                selectedDate: prev.selectedDate ?? todayIso,
              }
            : prev,
        )
        // Prefetches every date in the window (not just today) - US2's Day
        // Selection strip needs a favorability ranking for all ~16 days.
        // Each is independently cached/deduped (requestedConditionsRef), so
        // this is harmless if the user already picked a different day
        // before this resolved.
        if (data) for (const d of data.days) requestConditions(trailId, d.date)
      })
      .catch(() =>
        setPanel((prev) => (prev.selectedTrailId === trailId ? { ...prev, weatherWindow: { status: 'error', days: [] } } : prev)),
      )

    // Each of the three loads independently (FR-013) - one slow/failing
    // call must not block the others' loading states.
    getTrailInfo(trailId)
      .then((data) =>
        setPanel((prev) =>
          prev.selectedTrailId === trailId ? { ...prev, overview: { status: 'ready', data } } : prev,
        ),
      )
      .catch(() =>
        setPanel((prev) =>
          prev.selectedTrailId === trailId ? { ...prev, overview: { status: 'error', data: null } } : prev,
        ),
      )

    getTrailActivity(trailId)
      .then((data) =>
        setPanel((prev) =>
          prev.selectedTrailId === trailId ? { ...prev, popularity: { status: 'ready', data } } : prev,
        ),
      )
      .catch(() =>
        setPanel((prev) =>
          prev.selectedTrailId === trailId ? { ...prev, popularity: { status: 'error', data: null } } : prev,
        ),
      )

    getTrailGeometry(trailId)
      .then((data) =>
        setPanel((prev) =>
          prev.selectedTrailId === trailId
            ? { ...prev, route: { status: data ? 'ready' : 'absent', data } }
            : prev,
        ),
      )
      .catch(() =>
        setPanel((prev) =>
          prev.selectedTrailId === trailId ? { ...prev, route: { status: 'error', data: null } } : prev,
        ),
      )
  }

  // FR-010: dismiss restores the map to exactly where it was before the
  // panel opened, no reload.
  function handleDismiss() {
    if (panel.mapViewBeforeOpen) mapHandleRef.current?.restoreView(panel.mapViewBeforeOpen)
    setPanel(EMPTY_PANEL)
  }

  return (
    <div className="flex h-screen w-screen bg-(--color-base-200)">
      <Sidebar />
      {/* The map fills this entire area; the panel is an absolutely
          positioned overlay within it (not a flex sibling that would push
          the map and leave a flat background gutter behind the panel) -
          it floats directly on top of the map, as its own card. */}
      <div className="relative flex-1">
        <Map
          ref={mapHandleRef}
          trails={trails}
          route={panel.route.data}
          selectedTrailId={panel.selectedTrailId}
          onSelectTrail={handleSelectTrail}
        />
        {panel.selectedTrailId && (
          <TrailPanel onDismiss={handleDismiss}>
            <TrailOverview state={panel.overview} />
            <PopularityChart state={panel.popularity} />
            {/* Day Selection ("best days to go") sits above the Weather
                section's predictions by design - pick which day looks best
                first, then the detail below is for that day. Both still
                read/write the same panel.selectedDate (constitution
                Principle IV), so this is purely a scroll-order choice, not
                a state-flow one. */}
            <DaySelectionSection
              selectedDate={panel.selectedDate}
              weatherWindow={panel.weatherWindow}
              conditionsByDate={panel.conditionsByDate}
              popularity={panel.popularity.data}
              windowDates={Array.from({ length: FORECAST_WINDOW_DAYS }, (_, i) => isoDate(addDays(new Date(), i)))}
              onSelectDate={setSelectedDate}
            />
            <WeatherSection
              selectedDate={panel.selectedDate}
              weatherWindow={panel.weatherWindow}
              conditionsByDate={panel.conditionsByDate}
              onChangeDate={setSelectedDate}
            />
          </TrailPanel>
        )}
      </div>
    </div>
  )
}

export default App
