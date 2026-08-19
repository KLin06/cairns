# Client

React/Vite/TypeScript frontend for the trail conditions app. Reads `server/`'s Postgres-backed
endpoints - see `specs/004-mvp-frontend-design/` for the design spec this was built from.

## Run

```bash
npm install
npm run dev
```

Requires `server/` running on `http://localhost:8000` (see `../server/README.md`).

## Structure

- `src/theme/` - the design-token system (`tokens.css`: colors, radii, typography for both
  `cairns-light`/`cairns-dark` themes) and `ThemeProvider`/`useTheme` (light/dark state,
  persisted to `localStorage`). Every component styles itself from these tokens - see
  `specs/004-mvp-frontend-design/contracts/design-tokens.md` for the actual contract.
- `src/api/trails.ts` - typed wrappers around `server/`'s `/trails/{id}/info`, `/activity`,
  `/geometry` endpoints, plus `listTrails()`.
- `src/components/` - `Map` (MapLibre GL, OSM raster tiles, Ontario-bounded), `Sidebar`
  (Explore/Saved/Favorited/Plans - only Explore is functional), `TrailPanel`/`TrailOverview`/
  `PopularityChart` (the trail detail panel's Overview section), `ThemeToggle`.

## Known scaffolding, not a permanent design choice

`listTrails()` currently reads a static fixture (`src/api/trailListFixture.json`, a one-time
export of the real `trails` table) instead of a real backend endpoint - no "list all eligible
trails" endpoint exists yet (today's backend only supports per-trail-id lookups). Swapping in the
real endpoint once it exists is a one-line change in `listTrails()`; see
`specs/004-mvp-frontend-design/contracts/trail-list-dependency.md` for the shape the real endpoint
should match. If trails are added to/removed from the backend, re-run the export command in that
function's file comment to refresh the fixture.

## Notable implementation details

- MapLibre's paint expressions (the route line color) can't consume the CSS `oklch()` custom
  properties the theme tokens use directly - `--color-accent-hex` in `theme/tokens.css` mirrors
  the accent as a plain hex value for that one consumer.
- MapLibre's own `NavigationControl` chrome hardcodes a white background/dark icons regardless of
  theme (its dark-icon CSS variant is gated on Windows' forced-colors mode, not a general dark
  theme) - `index.css` inverts it under `[data-theme='cairns-dark']`.
- Tailwind v4 arbitrary-value color utilities referencing a CSS custom property need the
  `bg-(--color-x)` parenthesis syntax, not `bg-[--color-x]` (the latter is silently treated as an
  invalid literal, not an error) - worth remembering if adding new token-based utility classes.
