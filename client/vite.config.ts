import { defineConfig } from 'vite'
import react, { reactCompilerPreset } from '@vitejs/plugin-react'
import babel from '@rolldown/plugin-babel'
import tailwindcss from '@tailwindcss/vite'

// https://vite.dev/config/
export default defineConfig({
  plugins: [
    react(),
    babel({ presets: [reactCompilerPreset()] }),
    tailwindcss(),
  ],
  // maplibre-gl instantiates its own worker via `new Worker(new URL(...))`
  // internally - Vite's dependency pre-bundling rewrites that file into
  // .vite/deps and breaks the URL the worker script resolves against,
  // so the worker (needed for tiling GeoJSON/vector sources, not raster)
  // silently fails to load. Excluding it from pre-bundling keeps the
  // original file layout intact.
  optimizeDeps: {
    exclude: ['maplibre-gl'],
  },
})
