# Implementation Plan: MVP Frontend Design

**Branch**: `004-mvp-frontend-design` | **Date**: 2026-08-19 | **Spec**: [spec.md](./spec.md)

**Input**: Feature specification from `/specs/004-mvp-frontend-design/spec.md`

## Summary

Build the map + trail-overview-panel MVP client on the existing React/Vite/MapLibre/Tailwind v4/
daisyUI scaffold (`client/`), replacing today's bare unstyled map with the app's full visual
language: neutral slate palette + single amber accent, pronounced rounded corners (daisyUI v5's
native `--radius-box`/`--radius-field` theme variables, pill-shaped buttons/chips), Inter
typography, light/dark theming via a daisyUI custom theme pair toggled through a small
theme-context + `localStorage`, and a persistent left sidebar (Explore functional, three sections
visibly disabled). No new UI framework, chart library, or state-management library is introduced -
the scope is small enough that React's built-in state/context and a hand-rolled SVG bar chart
cover it without new dependencies beyond a self-hosted Inter font package.

## Technical Context

**Language/Version**: TypeScript 6 / React 19, on the existing Vite 8 toolchain (`client/`) - no
new language/runtime introduced.

**Primary Dependencies**: React 19, MapLibre GL JS (already in use for the map), Tailwind CSS v4 +
daisyUI v5 (already installed, currently unused beyond the CSS-reset import) - all existing. One
new dependency: `@fontsource-variable/inter` (self-hosted Inter, avoids a runtime call to Google
Fonts' CDN and keeps the font under the project's own build rather than an external dependency at
request time).

**Storage**: N/A for this feature's own data - the client reads the existing
`/trails/{id}/info`, `/activity`, `/geometry` endpoints (already Postgres-backed per specs
002/003) and the assumed-but-not-yet-built trail-listing endpoint (spec's Assumptions). The one
piece of client-side persistence this feature adds is the light/dark theme choice, in
`localStorage` (FR-021) - no backend storage involved.

**Testing**: No test framework is currently configured in `client/` (only `eslint` is wired up in
`package.json`). Given this feature is UI/visual and the project's existing test investment is
entirely on `server/` (pytest), this plan does not introduce a frontend test framework - visual/
interaction correctness is verified via the quickstart.md manual walkthrough against the acceptance
scenarios in spec.md, consistent with how UI work has been verified elsewhere in this project so
far (per repo convention: "start the dev server and use the feature in a browser").

**Target Platform**: Desktop/laptop browsers (spec FR-025 - no mobile/responsive target for this
feature), served by Vite's dev server locally (`npm run dev`, already configured in
`.claude/launch.json`).

**Project Type**: Web frontend - single existing project (`client/`), no new top-level project.

**Performance Goals**: Not specified numerically by the spec beyond SC-001's interaction-time
target ("under 10 seconds of interaction" to view a trail's Overview) - satisfied structurally by
data being fetched only for the clicked trail (not all trails' full detail up front) and by the
panel rendering immediately with per-field loading states (FR-013) rather than blocking on all
data before showing anything.

**Constraints**:
- Constitution Principle V (Single Continuous Scroll, No Tabbed Navigation): the Overview section
  is the only panel content in this scope, so there's nothing to scroll-segment yet, but the panel
  structure must not introduce tab-routing now that would conflict with the full panel (Weather,
  Day-selection) being added as more scroll sections later, per that principle.
- Constitution Principle IV (Shared Date State): not yet applicable - no date-dependent section
  exists in this scope (Weather/Day-selection are explicitly deferred), so there is no shared date
  state to wire up yet. Noted so the later feature that adds those sections doesn't have to retrofit
  this one.
- Spec FR-002/FR-024: Saved/Favorited/Plans must be visibly present but genuinely inert - no
  routing, no state, no stub API calls for them.
- Spec FR-019-022: both themes must be fully designed and applied via one token system, not a
  light theme with a naive CSS `filter: invert()` or similar shortcut.

**Scale/Scope**: ~68 trails today (per the backfilled dataset) - no virtualization, pagination, or
marker-clustering performance work is warranted at this scale; noted in research.md as a
deliberately deferred concern if the trail count grows substantially later.

## Constitution Check

*GATE: Must pass before Phase 0 research. Re-check after Phase 1 design.*

| Principle | Check | Result |
|---|---|---|
| I. Endpoint Separation | Not applicable - this feature adds no backend endpoints | N/A |
| II. Feature Parity (Training/Inference) | Not applicable - no model features involved | N/A |
| III. Forecast Horizon Hard Boundary | Not applicable - no weather/forecast UI in this scope | N/A |
| IV. Shared Date State Across the UI | Not applicable yet - no date-dependent section exists in this scope; the panel design must not preclude wiring shared date state in later, but there's nothing to violate today | N/A (forward-compatible) |
| V. Single Continuous Scroll, No Tabbed Navigation | The panel has exactly one section (Overview) in this scope, rendered as plain scrollable content, not a tab - future sections slot in as more scroll content per this principle, not new tabs | PASS |
| VI. Popularity Granularity Honesty | Only the monthly popularity chart is in scope (FR-012); day-of-week popularity is correctly *not* shown as its own chart here, since this feature has no "upcoming dates" surface (best-days strip) to anchor it to yet | PASS |
| VII. Pipeline-Gated Trail Data | Markers are sourced only from the assumed trail-listing endpoint, which spec's Assumptions ties to the same pipeline-gated backend data (specs 002/003) - the client does not independently query OSM or any other trail source | PASS |
| VIII. Honest Uncertainty in Predictions | Not applicable - no predictions surfaced in this scope (Conditions section deferred) | N/A |
| IX. Selective Field Storage | Not applicable - no new storage introduced | N/A |
| X. Scoped JSONB Usage | Not applicable - no new storage introduced | N/A |

No violations. Complexity Tracking table is not needed.

**Post-design re-check**: Phase 1 artifacts (data-model.md, contracts/) confirmed against the
table above - the design-tokens contract introduces no date-state coupling (Principle IV still
open, not violated), the panel-structure contract keeps Overview as plain scroll content with no
tab component (Principle V holds), and the trail-list dependency contract only requests
identity/location/coordinates, nothing that would let the client bypass the pipeline gate
(Principle VII holds). No drift from the constraints above.

## Project Structure

### Documentation (this feature)

```text
specs/004-mvp-frontend-design/
├── plan.md              # This file
├── research.md          # Phase 0 output
├── data-model.md        # Phase 1 output - frontend-side entities/state shapes
├── quickstart.md        # Phase 1 output
└── contracts/            # Phase 1 output
    ├── design-tokens.md  # Color/radius/typography/spacing token contract every component follows
    └── trail-list-dependency.md   # Expected shape of the not-yet-built trail-listing endpoint
```

### Source Code (repository root)

```text
client/
├── src/
│   ├── theme/
│   │   ├── tokens.css          # NEW - @theme block: colors, --radius-box/--radius-field,
│   │   │                          spacing scale, font-family (design-tokens.md contract)
│   │   ├── ThemeProvider.tsx   # NEW - light/dark context + localStorage persistence (FR-019-021)
│   │   └── useTheme.ts         # NEW - hook consuming ThemeProvider
│   ├── api/
│   │   └── trails.ts           # NEW - typed fetch wrappers: listTrails(), getTrailInfo(id),
│   │                              getTrailActivity(id), getTrailGeometry(id)
│   ├── components/
│   │   ├── Map.tsx             # MODIFIED - existing file: markers from listTrails() instead of
│   │   │                          the one hardcoded DEMO_TRAIL_ID, click-to-select wiring
│   │   ├── Sidebar.tsx         # NEW - four sections, Explore active/functional, rest disabled
│   │   ├── TrailPanel.tsx      # NEW - docked panel shell, full-height-immediately, dismiss
│   │   ├── TrailOverview.tsx   # NEW - name/difficulty/length/duration/surface/features
│   │   ├── PopularityChart.tsx # NEW - hand-rolled 12-bar SVG monthly chart (no chart library)
│   │   └── ThemeToggle.tsx     # NEW - light/dark switch control
│   ├── App.tsx                  # MODIFIED - existing file: sidebar + map + panel composition
│   └── index.css                 # MODIFIED - existing file: imports theme/tokens.css, daisyUI
│                                    theme block(s)
└── package.json                  # MODIFIED - existing file: add @fontsource-variable/inter
```

**Structure Decision**: Everything lives inside the existing `client/` project - no new
top-level project, no `frontend/`+`backend/` split (the repo already has that split at the
`client/`/`server/` level). New code is organized by concern (`theme/`, `api/`, `components/`)
rather than by page, since there is exactly one page in this scope; a `pages/` directory would be
premature structure for a single-screen feature. `Map.tsx` and `App.tsx` are modified in place
rather than rewritten, preserving the existing MapLibre setup (OSM raster style, Ontario bounds)
this feature doesn't relitigate.

## Complexity Tracking

*No Constitution Check violations - this section is not needed.*
