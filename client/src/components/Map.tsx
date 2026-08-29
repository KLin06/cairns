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
      // Stock OSM raster tiles read as a cartoonish, unstyled tutorial demo
      // (saturated green/tan/blue) next to everything else in this app.
      // These are WebGL raster paint properties (per-layer), not a CSS
      // filter on the canvas - a canvas-level filter would also mute the
      // accent-colored cluster circles/route line painted on the same
      // canvas in layers above this one, which is not the goal here.
      paint: {
        'raster-saturation': -0.35,
        'raster-contrast': -0.05,
        'raster-brightness-max': 0.96,
      },
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
const TRAILS_SOURCE_ID = 'trails'
const CLUSTERS_LAYER_ID = 'clusters'
const CLUSTER_COUNT_LAYER_ID = 'cluster-count'

// MapLibre paint expressions can't consume oklch() CSS custom properties
// directly - --color-accent-hex (theme/tokens.css) is the same accent as a
// plain hex value MapLibre's own color parser can resolve.
function getAccentColor(): string {
  return getComputedStyle(document.documentElement).getPropertyValue('--color-accent-hex').trim() || '#d97706'
}

// The cluster circles' stroke ring, so two nearby-but-separate clusters
// (or a cluster sitting on a busy stretch of tiles) stay visually distinct
// instead of blending into the map or each other.
function getBaseColor(): string {
  return getComputedStyle(document.documentElement).getPropertyValue('--color-base-100-hex').trim() || '#ffffff'
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

  // FR-005/FR-006, plus clustering for dense areas: MapLibre's native
  // clustering only works on a GeoJSON source rendered via layers (circle/
  // symbol), not on individual maplibregl.Marker DOM elements - so this is
  // a hybrid. A clustered GeoJSON source + two canvas layers draws the
  // cluster circles (accent-colored, sized by count); the existing DOM pin
  // markers (teardrop shape, black hole, active-state scale-up) are kept,
  // but only for trails that are CURRENTLY unclustered at the current
  // zoom/viewport - querySourceFeatures tells us which those are, re-run on
  // every 'data'/'moveend' so the pin set updates as the user pans/zooms.
  const trailsByIdRef = useRef(new globalThis.Map<string, TrailMarker>())
  trailsByIdRef.current = new globalThis.Map(trails.map((t) => [t.trailId, t]))

  useEffect(() => {
    const map = mapRef.current
    if (!map) return

    const geojson: GeoJSON.FeatureCollection<GeoJSON.Point, { trailId: string }> = {
      type: 'FeatureCollection',
      features: trails.map((t) => ({
        type: 'Feature',
        properties: { trailId: t.trailId },
        geometry: { type: 'Point', coordinates: [t.longitude, t.latitude] },
      })),
    }

    function createPinMarker(trail: TrailMarker): maplibregl.Marker {
      const el = document.createElement('div')
      el.className = 'trail-marker'
      el.setAttribute('role', 'button')
      el.setAttribute('aria-label', trail.name)
      // viewBox is padded 1 unit beyond the pin's own 0-24/0-32 bounds (not
      // 0 0 24 32 tightly) - the pin's top point and the circle's left/right
      // extremes all sit exactly on those original edges, and an SVG stroke
      // is centered on the path by default, so half of it painted outside
      // the tight viewBox and was getting clipped by the SVG's default
      // overflow:hidden (most visible at the top). The bottom edge (32)
      // stays untouched since the pin's tip sits there and anchor:'bottom'
      // below depends on it lining up with the element's actual bottom.
      //
      // Center hole: a plain solid black circle, not a transparent mask
      // cutout - simpler, and reads as a deliberate "pin head" hole against
      // any map tile color instead of showing whatever's underneath.
      el.innerHTML = `<svg viewBox="-1 -1 26 33" width="23" height="30"><path class="trail-marker-pin" d="${PIN_PATH}"/><circle class="trail-marker-hole" cx="12" cy="12" r="4"/></svg>`
      el.addEventListener('click', (e) => {
        e.stopPropagation()
        onSelectTrailRef.current(trail.trailId, {
          center: map!.getCenter().toArray() as [number, number],
          zoom: map!.getZoom(),
        })
      })
      // anchor: 'bottom' - the pin's tip (the path's point at y=32), not
      // its bounding-box center, is what marks the trail's coordinate.
      return new maplibregl.Marker({ element: el, anchor: 'bottom' })
        .setLngLat([trail.longitude, trail.latitude])
        .addTo(map!)
    }

    // Re-derives which trails are currently unclustered (individually
    // visible) and reconciles the DOM marker set to match - adds pins for
    // newly-unclustered trails, removes pins for trails that just merged
    // into a cluster (or panned out of the loaded tile set entirely).
    function refreshPins() {
      const features = map!.querySourceFeatures(TRAILS_SOURCE_ID, {
        filter: ['!', ['has', 'point_count']],
      })
      const unclusteredIds = new Set(features.map((f) => String(f.properties?.trailId)))

      for (const [trailId, marker] of markersRef.current) {
        if (!unclusteredIds.has(trailId)) {
          marker.remove()
          markersRef.current.delete(trailId)
        }
      }
      for (const trailId of unclusteredIds) {
        if (markersRef.current.has(trailId)) continue
        const trail = trailsByIdRef.current.get(trailId)
        if (!trail) continue
        markersRef.current.set(trailId, createPinMarker(trail))
      }
    }

    function onClusterClick(e: maplibregl.MapMouseEvent) {
      const features = map!.queryRenderedFeatures(e.point, { layers: [CLUSTERS_LAYER_ID] })
      const clusterId = features[0]?.properties?.cluster_id
      const source = map!.getSource(TRAILS_SOURCE_ID) as maplibregl.GeoJSONSource | undefined
      if (clusterId === undefined || !source) return
      source
        .getClusterExpansionZoom(clusterId)
        .then((zoom) => {
          map!.easeTo({ center: (features[0].geometry as GeoJSON.Point).coordinates as [number, number], zoom })
        })
        .catch(() => {})
    }

    function setUp() {
      const existingSource = map!.getSource(TRAILS_SOURCE_ID)
      if (existingSource && existingSource.type === 'geojson') {
        ;(existingSource as maplibregl.GeoJSONSource).setData(geojson)
        refreshPins()
        return
      }

      map!.addSource(TRAILS_SOURCE_ID, {
        type: 'geojson',
        data: geojson,
        cluster: true,
        clusterMaxZoom: 14,
        // clusterRadius is the max screen-pixel distance between points for
        // them to merge into one cluster - 50px was grouping markers that
        // read as clearly separate locations on screen. Smaller radius =
        // markers must be closer together before they're treated as "the
        // same area", so distant markers stay as their own pins/clusters.
        clusterRadius: 30,
      })
      map!.addLayer({
        id: CLUSTERS_LAYER_ID,
        type: 'circle',
        source: TRAILS_SOURCE_ID,
        filter: ['has', 'point_count'],
        paint: {
          'circle-color': getAccentColor(),
          // Bigger clusters read darker/more opaque, not just numerically
          // larger - a density cue you can read without parsing the count
          // label, the way a heatmap legend would.
          'circle-opacity': ['step', ['get', 'point_count'], 0.55, 5, 0.7, 10, 0.85, 25, 0.95],
          'circle-radius': ['step', ['get', 'point_count'], 12, 5, 16, 10, 20, 25, 24],
          // A ring around every cluster (in the theme's own base color, not
          // a fixed white/black) so adjacent clusters that are close on
          // screen but didn't merge stay legibly separate instead of
          // visually bleeding into one blob.
          'circle-stroke-color': getBaseColor(),
          'circle-stroke-width': ['step', ['get', 'point_count'], 1.5, 10, 2, 25, 2.5],
        },
      })
      map!.addLayer({
        id: CLUSTER_COUNT_LAYER_ID,
        type: 'symbol',
        source: TRAILS_SOURCE_ID,
        filter: ['has', 'point_count'],
        layout: { 'text-field': ['get', 'point_count_abbreviated'], 'text-size': 12, 'text-font': ['Noto Sans Bold'] },
        paint: { 'text-color': '#ffffff' },
      })

      map!.on('click', CLUSTERS_LAYER_ID, onClusterClick)
      map!.on('mouseenter', CLUSTERS_LAYER_ID, () => {
        map!.getCanvas().style.cursor = 'pointer'
      })
      map!.on('mouseleave', CLUSTERS_LAYER_ID, () => {
        map!.getCanvas().style.cursor = ''
      })
      map!.on('data', refreshPins)
      map!.on('moveend', refreshPins)
      refreshPins()
    }

    if (mapReadyRef.current) setUp()
    else map.once('load', setUp)

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
      if (map.getLayer(CLUSTERS_LAYER_ID)) {
        map.setPaintProperty(CLUSTERS_LAYER_ID, 'circle-color', getAccentColor())
        map.setPaintProperty(CLUSTERS_LAYER_ID, 'circle-stroke-color', getBaseColor())
      }
    })
    observer.observe(document.documentElement, { attributes: true, attributeFilter: ['data-theme'] })
    return () => observer.disconnect()
  }, [])

  return (
    <div className="relative h-full w-full">
      <div ref={containerRef} className="h-full w-full" />
      {/* Legend: nothing on the map itself explains why some trails render
          as a pin and others as a numbered circle - a one-time visual
          glossary, styled with the same card/rounded-box/border language as
          the trail panel rather than the map's own default chrome. */}
      <div className="pointer-events-none absolute left-4 top-4 flex flex-col gap-1.5 rounded-box border border-(--color-border) bg-(--color-base-100)/90 px-3 py-2 text-xs text-(--color-base-content) shadow-lg backdrop-blur-sm">
        <div className="flex items-center gap-2">
          <svg width="12" height="16" viewBox="-1 -1 26 33" aria-hidden="true">
            <path fill="var(--color-accent-hex)" stroke="var(--color-base-100)" strokeWidth="1" d={PIN_PATH} />
          </svg>
          <span>Single trail</span>
        </div>
        <div className="flex items-center gap-2">
          <span
            className="flex h-4 w-4 items-center justify-center rounded-full text-[9px] font-bold text-white"
            style={{ backgroundColor: 'var(--color-accent-hex)' }}
          >
            3
          </span>
          <span>Multiple trails</span>
        </div>
      </div>
    </div>
  )
})

export default Map
