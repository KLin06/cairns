# Phase 0 Research: MVP Frontend Design

No `[NEEDS CLARIFICATION]` markers remain in spec.md - the extensive clarifying-question rounds
before drafting resolved every open scope/visual-design question. What's left for this phase is
the technical "how" decisions the spec deliberately left to planning.

## 1. Theming mechanism (light/dark, design tokens)

**Decision**: Tailwind v4's CSS-first `@theme` block plus daisyUI v5's native theme variables
(`--radius-box` for cards/panel/popups, `--radius-field` for buttons/inputs, `--radius-selector`
for chips/toggles), defined as two named daisyUI themes (`cairns-light`, `cairns-dark`) via
`@plugin "daisyui/theme"` blocks in `client/src/theme/tokens.css`. Theme switching is a
`data-theme` attribute on `<html>`, toggled by a small `ThemeProvider` context that reads/writes
`localStorage` and falls back to the light theme default (FR-020) when nothing is stored.

**Rationale**: daisyUI v5 (already installed) is specifically built around exactly the three
component-category radius variables this spec's corner-rounding requirement (FR-014) needs - using
them means every daisyUI-based component (button, card, input) picks up the rounded-corner
language automatically instead of needing per-component radius overrides. Defining both themes as
real named daisyUI themes (not a single palette inverted via a CSS filter) directly satisfies
FR-019's "fully designed, not partial/inverted-only" requirement. This is additive to the existing
`@plugin "daisyui"` line in `index.css` - no new dependency.

**Alternatives considered**:
- Plain Tailwind `dark:` variant classes sprinkled through components, no daisyUI theme system -
  rejected: works, but means every component individually owns both color states instead of one
  central token definition, and doesn't get daisyUI's radius-variable-per-category structure for
  free.
- A CSS-in-JS theming library (styled-components, vanilla-extract, etc.) - rejected: introduces a
  new dependency and paradigm the rest of the project (plain Tailwind utility classes) doesn't use
  anywhere; no problem here actually needs it.

## 2. Font loading

**Decision**: `@fontsource-variable/inter` (self-hosted, single variable-weight font file),
imported once in `client/src/theme/tokens.css`, referenced via the `@theme`'s `--font-sans` token.

**Rationale**: Avoids a render-blocking or FOUC-prone runtime request to Google Fonts' CDN, keeps
the font asset inside the project's own build/bundle (consistent with this repo's general
preference for self-contained, minimal-external-dependency tooling), and a variable font means one
file covers the whole weight range this spec's typography scale (FR-016) needs instead of several
static-weight files.

**Alternatives considered**:
- `<link>` to Google Fonts CDN in `index.html` - rejected: an external network dependency at page
  load for something a ~150KB self-hosted variable font file solves without one.
- System font stack (no webfont) - this was explicitly asked about and not chosen (user picked
  "Modern grotesk sans-serif" over "System font stack") in the clarifying-questions round before
  drafting spec.md.

## 3. Monthly popularity chart

**Decision**: A small hand-rolled `PopularityChart` component rendering 12 bars as inline SVG
`<rect>` elements (or simple flex `<div>`s with height driven by a CSS custom property per bar),
styled with the accent-color token, no charting library.

**Rationale**: The chart is exactly 12 fixed-position bars with no interactivity beyond a possible
hover tooltip - well within what a ~30-line component can do directly. Pulling in a charting
library (Recharts, visx, Chart.js, etc.) for a single fixed bar chart would be the kind of
premature-dependency choice this project's stated engineering norms (minimal-dependency,
`data/scripts/`'s own plain-Python style, `server/`'s raw-`psycopg2`-over-ORM choice in spec 003)
consistently avoid elsewhere in this repo.

**Alternatives considered**:
- Recharts/visx - rejected per the above; would be justified if this feature also needed the
  16-day best-days chart or weather mini-strip, but those are explicitly deferred (spec FR-023).
- A `<canvas>`-based chart - rejected: no benefit over SVG/DOM for 12 static bars, and SVG/DOM
  bars are simpler to theme (light/dark) and style (rounded bar tops, matching FR-014) via plain
  CSS.

## 4. Data fetching / loading-state pattern

**Decision**: Plain `fetch()` wrapped in small typed functions (`client/src/api/trails.ts`), each
called from a small custom hook per data need (e.g. `useTrailOverview(trailId)`) that tracks
`{status: 'loading' | 'ready' | 'error', data}` in local component state - no data-fetching
library (React Query, SWR, etc.).

**Rationale**: `Map.tsx` already does a raw `fetch().then()` for geometry today; this continues
that pattern rather than introducing a new one, and the scope's actual data-fetching needs (one
trail-listing call on mount, three per-trail calls on marker click, no mutations, no cross-
component cache sharing needed since only one trail's panel is ever open at a time per FR-007) 
don't need a caching/invalidation library to satisfy FR-013's per-field loading-state requirement.

**Alternatives considered**:
- React Query/SWR - reasonable, especially if a later feature adds more data-dependent sections
  (Weather/Conditions) that would benefit from shared caching - but not justified by this feature's
  scope alone; worth reconsidering when that later feature is planned, not here.

## 5. Trail-list dependency shape

**Decision**: Not building the endpoint (per spec's Assumptions, explicitly out of scope), but the
frontend's `listTrails()` function needs a concrete shape to code against now. Documented as an
assumed contract in `contracts/trail-list-dependency.md` (id + name + coordinates only - the
minimum a map marker needs) so the eventual backend work has a clear target and this feature isn't
blocked guessing at a shape mid-implementation.

**Rationale**: `data-model.md`'s `Trail marker` entity only needs identity and location (per
spec.md) - deliberately not the full `/info` payload, since that's fetched separately per-trail
only when its panel opens (FR-007), keeping the initial map load lightweight (a large `/info`-style
payload for every one of ~68+ trails up front would be wasteful when only one trail's detail is
ever shown at a time).

**Alternatives considered**:
- Fetching every trail's full `/info` on load and deriving markers from that - rejected: far more
  data than markers need, and defeats the point of a lightweight listing endpoint existing at all
  (this was the exact reasoning that motivated proposing a map-markers endpoint as the project's
  next backend step in prior work).
