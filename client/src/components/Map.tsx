import { useEffect, useRef } from 'react'
import * as maplibregl from 'maplibre-gl'
import 'maplibre-gl/dist/maplibre-gl.css'

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

// Track and Tower Trail, Algonquin Provincial Park - first test marker,
// coords from the trail's _geoloc in the explore pipeline data.
const TRACK_AND_TOWER: [number, number] = [-78.57765, 45.55999]

export default function Map() {
  const containerRef = useRef<HTMLDivElement>(null)
  const mapRef = useRef<maplibregl.Map | null>(null)

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

    new maplibregl.Marker()
      .setLngLat(TRACK_AND_TOWER)
      .setPopup(new maplibregl.Popup().setText('Track and Tower Trail'))
      .addTo(map)

    mapRef.current = map

    return () => {
      map.remove()
      mapRef.current = null
    }
  }, [])

  return <div ref={containerRef} className="h-full w-full" />
}
