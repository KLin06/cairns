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

// Cup and Saucer Trail, Manitoulin Island - first test marker, coords from
// the trail's _geoloc in the explore pipeline data. (Track and Tower was
// the original placeholder here, but its route geometry couldn't be
// fetched during dev due to an AllTrails bot-protection block on our
// network - Cup and Saucer already has verified geometry on disk.)
const DEMO_TRAIL_ID = '10024848'
const DEMO_TRAIL_CENTER: [number, number] = [-82.11391, 45.85331]

const API_BASE = 'http://localhost:8000'

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
      .setLngLat(DEMO_TRAIL_CENTER)
      .setPopup(new maplibregl.Popup().setText('Cup and Saucer Trail'))
      .addTo(map)

    map.on('load', () => {
      fetch(`${API_BASE}/trails/${DEMO_TRAIL_ID}/geometry`)
        .then((res) => {
          if (!res.ok) throw new Error(`geometry fetch failed: ${res.status}`)
          return res.json()
        })
        .then((geojson: maplibregl.GeoJSONSourceSpecification['data']) => {
          map.addSource('demo-trail-route', { type: 'geojson', data: geojson })
          map.addLayer({
            id: 'demo-trail-route',
            type: 'line',
            source: 'demo-trail-route',
            layout: { 'line-join': 'round', 'line-cap': 'round' },
            paint: { 'line-color': '#e8590c', 'line-width': 4 },
          })

          const coords = (geojson as GeoJSON.FeatureCollection).features.flatMap(
            (f) => (f.geometry as GeoJSON.LineString).coordinates as [number, number][],
          )
          if (coords.length > 0) {
            const bounds = coords.reduce(
              (b, c) => b.extend(c),
              new maplibregl.LngLatBounds(coords[0], coords[0]),
            )
            map.fitBounds(bounds, { padding: 60 })
          }
        })
        .catch((err) => console.error('failed to load trail geometry', err))
    })

    mapRef.current = map

    return () => {
      map.remove()
      mapRef.current = null
    }
  }, [])

  return <div ref={containerRef} className="h-full w-full" />
}
