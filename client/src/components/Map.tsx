import { forwardRef, useEffect, useImperativeHandle, useRef } from 'react'
import * as maplibregl from 'maplibre-gl'
import 'maplibre-gl/dist/maplibre-gl.css'
import type { TrailMarker } from '../api/trails'

// OSM raster tiles wrapped in a MapLibre style - no API key required. True
// vector OSM tiles need a paid provider (MapTiler, etc.); this keeps the
// "free, no key" constraint from the spec while still getting MapLibre's
// WebGL pan/zoom/rendering, and lets us layer vector markers/overlays
// (trail pins, route lines) on top later without switching renderers.
const OSM_STYLE: maplibregl.StyleSpecification = {
  version: 8,
  sources: {
    osm: {
      type: 'raster',
      tiles: ['https://tile.openstreetmap.org/{z}/{x}/{y}.png'],
      tileSize: 256,
      attribution: '&copy; <a href="https://www.openstreetmap.org/copyright">OpenStreetMap</a> contributors',
    },
  },
  layers: [
    {
      id: 'osm',
      type: 'raster',
      source: 'osm',
    },
  ],
}

// Ontario, roughly centered on the trails currently in the pipeline.
const INITIAL_CENTER: [number, number] = [-81.3, 46.0]
const INITIAL_ZOOM = 6

// Ontario's own bounding box (same one used to scope the trail-explore
// pipeline scripts), scaled 1.3x around its center for some pan buffer
// beyond the strict border - keeps panning/zooming from wandering off to
// places with no trail data to show. [west, south], [east, north].
const ONTARIO_BOUNDS: maplibregl.LngLatBoundsLike = [
  [-98.2767, 39.3855],
  [-71.2221, 59.241],
]

const ROUTE_SOURCE_ID = 'selected-trail-route'

// MapLibre paint expressions can't consume oklch() CSS custom properties
// directly - --color-accent-hex (theme/tokens.css) is the same accent as a
// plain hex value MapLibre's own color parser can resolve.
function getAccentColor(): string {
  return getComputedStyle(document.documentElement).getPropertyValue('--color-accent-hex').trim() || '#d97706'
}

export interface MapView {
  center: [number, number]
  zoom: number
}

export interface MapHandle {
  restoreView: (view: MapView) => void
}

interface MapProps {
  trails: TrailMarker[]
  route: GeoJSON.FeatureCollection | null
  selectedTrailId: string | null
  onSelectTrail: (trailId: string, viewBeforeSelect: MapView) => void
}

// Classic map-pin silhouette (rounded head, pointed tip) - viewBox is sized
// so the tip sits exactly at (12, 32), which is what the marker is anchored
// to below (anchor: 'bottom').
const PIN_PATH = 'M12 0C5.4 0 0 5.4 0 12c0 9 12 20 12 20s12-11 12-20c0-6.6-5.4-12-12-12z'

const Map = forwardRef<MapHandle, MapProps>(function Map({ trails, route, selectedTrailId, onSelectTrail }, ref) {
  const containerRef = useRef<HTMLDivElement>(null)
  const mapRef = useRef<maplibregl.Map | null>(null)
  // globalThis.Map, not the bare `Map` type: the named function expression
  // above (`function Map(...)`) shadows the global Map identifier within
  // this component's own body.
  const markersRef = useRef<globalThis.Map<string, maplibregl.Marker>>(new globalThis.Map())
  // map.loaded() reflects tile-loading state (flaps as you pan) and
  // isStyleLoaded() has its own edge cases - neither reliably answers "has
  // the 'load' event already fired". A plain ref set exactly once inside
  // the 'load' handler avoids racing effects that run after 'load' already
  // fired registering a `.once('load', ...)` listener that then never fires.
  const mapReadyRef = useRef(false)
  // Held in a ref (not state) since onSelectTrail/restoreView are called
  // from map event handlers/imperative calls, not React's render cycle.
  const onSelectTrailRef = useRef(onSelectTrail)
  onSelectTrailRef.current = onSelectTrail

  useImperativeHandle(ref, () => ({
    restoreView(view) {
      mapRef.current?.jumpTo({ center: view.center, zoom: view.zoom })
    },
  }))

  // Map instance: created once, never re-created on prop changes.
  useEffect(() => {
    if (!containerRef.current || mapRef.current) return

    const map = new maplibregl.Map({
      container: containerRef.current,
      style: OSM_STYLE,
      center: INITIAL_CENTER,
      zoom: INITIAL_ZOOM,
      maxBounds: ONTARIO_BOUNDS,
    })
    map.addControl(new maplibregl.NavigationControl(), 'top-right')
    map.once('load', () => {
      mapReadyRef.current = true
    })
    mapRef.current = map

    return () => {
      map.remove()
      mapRef.current = null
      mapReadyRef.current = false
    }
  }, [])

  // FR-005/FR-006: one accent-colored pin marker per eligible trail.
  // Unlike the route layer below, maplibregl.Marker doesn't need the style
  // or tiles to be loaded - it's a plain DOM element positioned via the
  // map's transform, which exists as soon as the Map instance is
  // constructed - so this deliberately does NOT gate on mapReadyRef/'load'.
  useEffect(() => {
    const map = mapRef.current
    if (!map) return

    for (const marker of markersRef.current.values()) marker.remove()
    const next = new globalThis.Map<string, maplibregl.Marker>()
    for (const trail of trails) {
      const el = document.createElement('div')
      el.className = 'trail-marker'
      el.setAttribute('role', 'button')
      el.setAttribute('aria-label', trail.name)
      el.innerHTML = `<svg viewBox="0 0 24 32" width="26" height="34"><path class="trail-marker-pin" d="${PIN_PATH}"/><circle class="trail-marker-hole" cx="12" cy="12" r="4.5"/></svg>`
      el.addEventListener('click', (e) => {
        e.stopPropagation()
        onSelectTrailRef.current(trail.trailId, {
          center: map.getCenter().toArray() as [number, number],
          zoom: map.getZoom(),
        })
      })
      // anchor: 'bottom' - the pin's tip (the path's point at y=32), not
      // its bounding-box center, is what marks the trail's coordinate.
      next.set(
        trail.trailId,
        new maplibregl.Marker({ element: el, anchor: 'bottom' }).setLngLat([trail.longitude, trail.latitude]).addTo(map),
      )
    }
    markersRef.current = next

    return () => {
      for (const marker of markersRef.current.values()) marker.remove()
      markersRef.current = new globalThis.Map()
    }
  }, [trails])

  // Visually marks the clicked/open trail's pin as active (FR: "when the
  // map pin is pressed, have a change to its UI to indicate it is active").
  useEffect(() => {
    for (const [trailId, marker] of markersRef.current) {
      marker.getElement().classList.toggle('trail-marker--active', trailId === selectedTrailId)
    }
  }, [selectedTrailId, trails])

  // FR-008: draw the selected trail's route when present, remove it when
  // not (no route on record, or panel dismissed) - never an error state.
  useEffect(() => {
    const map = mapRef.current
    if (!map) return

    function syncRoute() {
      const existingSource = map!.getSource(ROUTE_SOURCE_ID)
      if (!route) {
        if (map!.getLayer(ROUTE_SOURCE_ID)) map!.removeLayer(ROUTE_SOURCE_ID)
        if (existingSource) map!.removeSource(ROUTE_SOURCE_ID)
        return
      }

      if (existingSource && existingSource.type === 'geojson') {
        ;(existingSource as maplibregl.GeoJSONSource).setData(route)
      } else {
        map!.addSource(ROUTE_SOURCE_ID, { type: 'geojson', data: route })
        map!.addLayer({
          id: ROUTE_SOURCE_ID,
          type: 'line',
          source: ROUTE_SOURCE_ID,
          layout: { 'line-join': 'round', 'line-cap': 'round' },
          paint: { 'line-color': getAccentColor(), 'line-width': 4 },
        })
      }
    }

    if (mapReadyRef.current) syncRoute()
    else map.once('load', syncRoute)
  }, [route])

  // FR-019: the route line is a WebGL paint expression, not CSS - it won't
  // pick up a theme switch on its own, so watch <html data-theme> directly.
  useEffect(() => {
    const map = mapRef.current
    if (!map) return

    const observer = new MutationObserver(() => {
      if (map.getLayer(ROUTE_SOURCE_ID)) {
        map.setPaintProperty(ROUTE_SOURCE_ID, 'line-color', getAccentColor())
      }
    })
    observer.observe(document.documentElement, { attributes: true, attributeFilter: ['data-theme'] })
    return () => observer.disconnect()
  }, [])

  return <div ref={containerRef} className="h-full w-full" />
})

export default Map
