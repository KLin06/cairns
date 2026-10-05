import { readFileSync } from 'node:fs'
import { createRequire } from 'node:module'
import { dirname, join } from 'node:path'
import { defineConfig, type Plugin } from 'vite'
import react, { reactCompilerPreset } from '@vitejs/plugin-react'
import babel from '@rolldown/plugin-babel'
import tailwindcss from '@tailwindcss/vite'

// maplibre-gl 6 builds its worker URL at runtime from import.meta.url, which
// Vite can't see, so the production build never ships the worker. The worker
// is also not self-contained: it does `import ... from "./maplibre-gl-shared.mjs"`
// (the engine itself), so BOTH files must be served side by side under their
// original names - emitting just the worker (e.g. via a `?url` import) leaves
// its sibling import 404ing and the worker silently dying. Copied from the
// installed package at build time so they can never drift from its version.
// Production only: `vite dev` keeps using maplibre's own default resolution
// (see optimizeDeps.exclude below). Map.tsx points setWorkerUrl at this path.
const MAPLIBRE_WORKER_DIR = 'maplibre'
function maplibreWorkerFiles(): Plugin {
  const distDir = join(dirname(createRequire(import.meta.url).resolve('maplibre-gl/package.json')), 'dist')
  return {
    name: 'maplibre-worker-files',
    apply: 'build',
    generateBundle() {
      for (const name of ['maplibre-gl-worker.mjs', 'maplibre-gl-shared.mjs']) {
        this.emitFile({ type: 'asset', fileName: `${MAPLIBRE_WORKER_DIR}/${name}`, source: readFileSync(join(distDir, name)) })
      }
    },
  }
}

// https://vite.dev/config/
export default defineConfig({
  plugins: [
    react(),
    babel({ presets: [reactCompilerPreset()] }),
    tailwindcss(),
    maplibreWorkerFiles(),
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
