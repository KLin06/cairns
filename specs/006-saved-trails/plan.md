# Implementation Plan: Saved Trails

**Branch**: `006-saved-trails` | **Date**: 2026-08-29 | **Spec**: [spec.md](./spec.md)

**Input**: Feature specification from `/specs/006-saved-trails/spec.md`

## Summary

Consolidate the sidebar's separate "Saved"/"Favorited" placeholders into one functional "Saved"
entry. Add a bookmark toggle to the trail panel's Overview section, backed by a single
`trailId -> savedAt` set persisted to `localStorage` (no server/database involvement). Add a new
saved-trails screen - a real navigation target that replaces the Explore map view, not an overlay
or the trail panel - offering a List view (rows of saved trails) and a Map view (the existing
`Map` component, pins filtered to the saved set), switched via one centered bottom-edge toggle.
All state (saved set, active sidebar section, list/map sub-view) is lifted into `App.tsx` so a
save/unsave from either the trail panel icon or the list row updates every currently-rendered view
in the same render, with no reload.

## Technical Context

**Language/Version**: TypeScript/React 19 (client only - no server changes)

**Primary Dependencies**: Existing client stack only - React, Tailwind v4/daisyUI, `maplibre-gl`
(via the existing `Map` component). No new runtime dependencies; no router library added (see
research.md decision 1).

**Storage**: Browser `localStorage` only, under one namespaced key. No Postgres/backend changes
(FR-015) - this feature does not touch `server/` at all.

**Testing**: No client test runner currently configured (same as spec 005) - manual browser
verification via the preview tools.

**Target Platform**: Local dev (Vite on :5173), same as existing client code. No new server
process/endpoint.

**Project Type**: Web application - this feature is entirely within the existing `client/`
package; `server/` and `data/scripts/` are untouched.

**Performance Goals**: No new goals stated; view-mode toggle and save/unsave must be synchronous
UI updates (SC-001, SC-003, SC-004 all require "no visible delay"/"same interaction").

**Constraints**: Must degrade silently (empty saved set, no crash) when `localStorage` is
unavailable or throws (private/incognito browsing) - edge case explicitly called out in spec.md.

**Scale/Scope**: One new client service module (`savedTrails.ts`), one new screen component
(`SavedTrailsScreen.tsx`) plus a small list-row/empty-state/toggle subcomponents, edits to three
existing client files (`App.tsx`, `Sidebar.tsx`, `TrailOverview.tsx`).

## Constitution Check

*GATE: Must pass before Phase 0 research. Re-checked after Phase 1 design.*

| Principle | Check | Status |
|---|---|---|
| I. Endpoint Separation | N/A - no endpoints added or touched | N/A |
| II. Feature Parity (training/inference) | N/A - no model involvement | N/A |
| III. Forecast Horizon | N/A - no weather/forecast involvement | N/A |
| IV. Shared Date State | N/A - feature has no date-selection surface | N/A |
| V. Single Continuous Scroll, No Tabs | Applies narrowly to the trail detail panel's own sections, which are unchanged (the bookmark icon is added inline to the existing Overview section, not a new scroll section or tab). The saved-trails screen's Map/List toggle is a *different screen*, not tabs inside the panel's scroll - not a violation | PASS |
| VI. Popularity Granularity Honesty | N/A - no popularity/review aggregation shown here | N/A |
| VII. Pipeline-Gated Trail Data | Saved-trails List/Map views are derived by filtering the existing `trails` (from `listTrails()`, already pipeline-gated) against the saved-id set - a saved id no longer present in that pipelined list is simply excluded (spec's documented edge case), never fetched from an external source | PASS |
| VIII. Honest Uncertainty | N/A - no predictions shown here | N/A |
| IX/X. Selective/Scoped Storage | N/A - no database schema touched; the one new persisted shape (`{trailId, savedAt}[]`) lives in `localStorage`, not Postgres | N/A |

No violations requiring Complexity Tracking.

## Project Structure

### Documentation (this feature)

```text
specs/006-saved-trails/
├── plan.md              # This file
├── research.md
├── data-model.md
├── quickstart.md
├── contracts/
│   └── saved-trails-storage.md
└── tasks.md              # /speckit-tasks output (not yet generated)
```

### Source Code (repository root)

```text
client/src/
├── savedTrails.ts                     # NEW - localStorage read/write for the saved set
├── App.tsx                            # + activeView state, saved-set state, toggleSaved,
│                                       #   swaps main content between Explore and Saved screen
├── components/
│   ├── Sidebar.tsx                    # Saved/Favorited merged into one enabled "Saved" entry;
│   │                                  #   takes activeView + onSelect props
│   ├── TrailOverview.tsx              # + bookmark icon/button in the Overview header, driven by
│   │                                  #   isSaved/onToggleSaved props
│   └── SavedTrailsScreen.tsx          # NEW - List/Map toggle, list rows, reuses Map + empty state
└── api/trails.ts                      # unchanged (TrailMarker already has what list rows need)
```

**Structure Decision**: No new top-level structure - this feature is additive within
`client/src/`, following the same "lift shared state into `App.tsx`, pass it down as props"
pattern spec 005 already established for `panel`/`selectedDate`. `server/` and `data/scripts/` are
untouched, consistent with the spec's explicit "no backend/database changes" constraint.

## Complexity Tracking

*No constitution violations - table not needed.*
