import { useEffect, useRef, useState } from 'react'
import Map, { type MapHandle, type MapView } from './components/Map'
import Sidebar from './components/Sidebar'
import TrailPanel from './components/TrailPanel'
import TrailOverview, { type OverviewState } from './components/TrailOverview'
import PopularityChart, { type PopularityState } from './components/PopularityChart'
import { getTrailActivity, getTrailGeometry, getTrailInfo, listTrails, type TrailMarker } from './api/trails'

interface RouteState {
  status: 'loading' | 'ready' | 'absent' | 'error'
  data: GeoJSON.FeatureCollection | null
}

// data-model.md's PanelState, held here since both Map and TrailPanel read/
// drive pieces of it.
interface PanelState {
  selectedTrailId: string | null
  overview: OverviewState
  popularity: PopularityState
  route: RouteState
  mapViewBeforeOpen: MapView | null
}

const EMPTY_PANEL: PanelState = {
  selectedTrailId: null,
  overview: { status: 'loading', data: null },
  popularity: { status: 'loading', data: null },
  route: { status: 'loading', data: null },
  mapViewBeforeOpen: null,
}

function App() {
  const mapHandleRef = useRef<MapHandle>(null)
  const [trails, setTrails] = useState<TrailMarker[]>([])
  const [panel, setPanel] = useState<PanelState>(EMPTY_PANEL)

  useEffect(() => {
    listTrails().then(setTrails).catch(console.error)
  }, [])

  // FR-007: clicking a marker (first time, or while a panel is already
  // open for a different trail) sets/updates this same panel state, never
  // unmounts/remounts TrailPanel.
  function handleSelectTrail(trailId: string, viewBeforeSelect: MapView) {
    setPanel((prev) => ({
      selectedTrailId: trailId,
      overview: { status: 'loading', data: null },
      popularity: { status: 'loading', data: null },
      route: { status: 'loading', data: null },
      // Only capture the view once - if a second marker is clicked while a
      // panel is already open, dismiss should still restore the view from
      // *before the first* selection, not the intermediate one.
      mapViewBeforeOpen: prev.mapViewBeforeOpen ?? viewBeforeSelect,
    }))

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
          </TrailPanel>
        )}
      </div>
    </div>
  )
}

export default App
