---

description: "Task list for MVP Frontend Design"
---

# Tasks: MVP Frontend Design

**Input**: Design documents from `/specs/004-mvp-frontend-design/`

**Prerequisites**: [plan.md](./plan.md), [spec.md](./spec.md), [research.md](./research.md), [data-model.md](./data-model.md), [contracts/](./contracts/), [quickstart.md](./quickstart.md)

**Tests**: Not included - plan.md's Technical Context notes no test framework is configured in
`client/` and this feature is verified via `quickstart.md`'s manual walkthrough against spec.md's
acceptance scenarios, consistent with how UI work is verified elsewhere in this project.

**Organization**: Tasks are grouped by user story (spec.md: US1/US2 are P1, US3/US4 are P2) to
enable independent implementation and testing of each.

## Path Conventions

Single existing project, `client/` (see plan.md's Structure Decision) - no new top-level project.

---

## Phase 1: Setup

**Purpose**: Add the one new dependency and scaffold the new directories this feature needs

- [X] T001 Add `@fontsource-variable/inter` to `client/package.json` and run `npm install` (research.md decision 2)
- [X] T002 [P] Create `client/src/theme/` directory with empty `tokens.css`, `ThemeProvider.tsx`, `useTheme.ts`
- [X] T003 [P] Create `client/src/api/` directory with an empty `trails.ts`

---

## Phase 2: Foundational (Blocking Prerequisites)

**Purpose**: The design-token system, theming infrastructure, and API layer every user story's UI
work builds on

**⚠️ CRITICAL**: No user story phase below can be completed until this phase is done

- [X] T004 Define the design tokens in `client/src/theme/tokens.css`: import `@fontsource-variable/inter`, a Tailwind v4 `@theme` block with `--font-sans`, and two daisyUI themes (`cairns-light`, `cairns-dark`) via `@plugin "daisyui/theme"` blocks setting `--color-base-100/-200/-300`, `--color-base-content`, `--color-neutral-content`, `--color-border`, `--color-accent`, `--color-accent-content`, `--radius-field` (~12-16px), `--radius-box` (~20-24px), `--radius-selector` (pill) - exactly the tokens contracts/design-tokens.md defines
- [X] T005 In `client/src/index.css`, import `./theme/tokens.css` alongside the existing `@import "tailwindcss";` and `@plugin "daisyui";` lines
- [X] T006 Implement `client/src/theme/ThemeProvider.tsx`: a React context holding `{mode: 'light' | 'dark', toggle: () => void}`, reading `localStorage["cairns-theme"]` on init (defaulting to `'light'` per FR-020 when unset), writing on change (FR-021), and setting `data-theme` on `document.documentElement` to `cairns-light`/`cairns-dark` to match
- [X] T007 [P] Implement `client/src/theme/useTheme.ts`: a hook consuming `ThemeProvider`'s context (depends on T006)
- [X] T008 In `client/src/main.tsx`, wrap `<App />` in `<ThemeProvider>`
- [X] T009 Implement `client/src/api/trails.ts`'s per-trail functions: `getTrailInfo(trailId)`, `getTrailActivity(trailId)`, `getTrailGeometry(trailId)` - typed `fetch()` wrappers against the existing `/trails/{id}/info`, `/activity`, `/geometry` endpoints (data-model.md's `TrailOverview`/`TrailPopularity`/`TrailRoute` shapes), each returning `null` on a 404 rather than throwing (matches FR-008's "absent geometry is not an error")
- [X] T010 Create `client/src/api/trailListFixture.json`: a static export of the real `trails` table's `trail_id`/`name`/`latitude`/`longitude`, shaped per contracts/trail-list-dependency.md (not hand-written fake data). Generate it by running, from `server/`: `venv/Scripts/python.exe -c "import os, json; from dotenv import load_dotenv; load_dotenv('.env'); import psycopg2; from psycopg2.extras import RealDictCursor; conn = psycopg2.connect(os.environ['DATABASE_URL']); cur = conn.cursor(cursor_factory=RealDictCursor); cur.execute('select trail_id, name, latitude, longitude from trails'); print(json.dumps({'trails': cur.fetchall()}))"` and saving the output to `client/src/api/trailListFixture.json` (reuses the same `DATABASE_URL`/`psycopg2` setup `server/db/backfill.py` already depends on - no new tooling introduced)
- [X] T011 Implement `client/src/api/trails.ts`'s `listTrails()`: reads `trailListFixture.json` (T010) behind the exact shape contracts/trail-list-dependency.md defines, so swapping in the real endpoint later is a one-line change (depends on T009, T010)

**Checkpoint**: Theming and data-fetching infrastructure exist. User story UI work can now begin.

---

## Phase 3: User Story 1 - Browse trails on the map and open one's overview (Priority: P1) 🎯 MVP

**Goal**: A user can see trail markers, click one, and see its Overview data in a panel that
opens/closes cleanly without disturbing the map.

**Independent Test**: quickstart.md step 2 - load the app, click a marker, confirm the panel opens
at full height immediately with all Overview fields and the route line, then dismiss and confirm
the map's pan/zoom is unchanged.

### Implementation for User Story 1

- [X] T012 [US1] In `client/src/components/Map.tsx`, replace the hardcoded `DEMO_TRAIL_ID`/`DEMO_TRAIL_CENTER` marker with one marker per entry from `listTrails()` (T011), each a simple accent-colored dot (FR-005, FR-006)
- [X] T013 [US1] In `client/src/components/Map.tsx`, add marker click handling that reports the clicked `trailId` to a parent-owned selection callback/prop, and captures the map's current `{center, zoom}` before any state change (data-model.md's `mapViewBeforeOpen`) (FR-007)
- [X] T014 [US1] Create `client/src/components/TrailPanel.tsx`: a panel docked to the map's edge, rendered at full height on its first frame (no grow/expand transition/animation), with a dismiss control; per contracts/design-tokens.md's documented exception, only the panel's map-facing corners use `--radius-box`, its outer viewport-edge corners stay square (FR-009)
- [X] T015 [US1] Create `client/src/components/TrailOverview.tsx`: renders name, difficulty rating, length, duration, surface type breakdown, and feature chips from a `TrailOverview` value, showing a loading placeholder per field while its data is pending (FR-012, FR-013)
- [X] T016 [P] [US1] Create `client/src/components/PopularityChart.tsx`: a hand-rolled 12-bar SVG/DOM chart from a `TrailPopularity.byMonth` value (research.md decision 3); renders correctly with all-zero values when `totalReviews` is 0 rather than erroring or hiding (Edge Cases)
- [X] T017 [US1] In `client/src/App.tsx`, own `PanelState` (data-model.md: `selectedTrailId`, per-field `overview`/`popularity`/`route` status objects, `mapViewBeforeOpen`); on `selectedTrailId` change, call `getTrailInfo`/`getTrailActivity`/`getTrailGeometry` (T009) independently so one slow/failing call doesn't block the others' loading states
- [X] T018 [US1] In `client/src/App.tsx`/`Map.tsx`, when `PanelState.route.data` is present, draw it as a GeoJSON line source/layer in the accent color (matching the existing demo-trail-route pattern already in `Map.tsx`); when `route.status === 'absent'` (404), draw nothing and treat it as normal, not an error (FR-008)
- [X] T019 [US1] Wire `TrailPanel`'s dismiss control to clear `selectedTrailId` and restore the map to `mapViewBeforeOpen` without a page reload (FR-010)
- [X] T020 [US1] Handle clicking a different marker while a panel is already open: update the existing `PanelState` to the new `trailId` (re-fetching all three data pieces) rather than unmounting/remounting `TrailPanel` (FR-007, Edge Cases)

**Checkpoint**: `npm run dev` in `client/`, click any marker → full Overview panel with route line;
dismiss → map unchanged. Independently testable and demoable.

---

## Phase 4: User Story 2 - Recognize a consistent, polished visual identity (Priority: P1)

**Goal**: Every element built in US1 (and the sidebar/theme toggle added later) visually reads as
one coherent design language - rounded corners, the neutral+accent palette, spacious padding,
border-only elevation - not a mix of styled and default-browser elements.

**Independent Test**: quickstart.md step 3 - visually scan every element in scope and confirm
consistent corner-rounding, exactly two hues in use, and generous spacing.

### Implementation for User Story 2

- [X] T021 [US2] Style `TrailPanel.tsx` (T014) per contracts/design-tokens.md: `--radius-box` on its map-facing corners, `border border-[--color-border]` with no/minimal shadow, spacious (`p-6`-class) section padding (FR-014, FR-017, FR-018)
- [X] T022 [US2] Style `TrailOverview.tsx` (T015): feature chips as fully pill-shaped (`--radius-selector`)/`rounded-full`, headings/body/meta text using the typography scale contracts/design-tokens.md defines, spacious internal padding (FR-014, FR-016, FR-017)
- [X] T023 [P] [US2] Style `PopularityChart.tsx` (T016): bars in `--color-accent`, rounded bar tops consistent with the radius language (FR-014, FR-015)
- [X] T024 [P] [US2] Style map markers and any popups in `Map.tsx` (T012) per contracts/design-tokens.md: accent-colored dot markers, `--radius-box`-rounded popup if one is used (FR-006, FR-014)
- [X] T025 [US2] Style `TrailPanel`'s dismiss control and any other buttons introduced in US1 as pill-shaped (`--radius-field` + `rounded-full`) using `--color-accent` for primary actions (FR-014, FR-015)
- [X] T026 [US2] Audit every element touched in US1 for any hardcoded color outside the neutral scale + `--color-accent`, or any unrounded/default-browser-styled element, and fix - this is the "zero unstyled elements" bar SC-002 sets

**Checkpoint**: US1's UI now fully matches the design language - the core browsing flow is both
functional and visually complete.

---

## Phase 5: User Story 3 - See where the rest of the app is headed without it being functional yet (Priority: P2)

**Goal**: The sidebar previews the full intended navigation (Explore/Saved/Favorited/Plans) with
only Explore actually working.

**Independent Test**: quickstart.md step 4 - confirm all four sections are visible, Explore is
active, and clicking the other three does nothing while looking visibly non-interactive.

### Implementation for User Story 3

- [X] T027 [US3] Create `client/src/components/Sidebar.tsx`: renders the four `SidebarSection`s from data-model.md (Explore/Saved/Favorited/Plans), Explore marked `active`/`enabled`, the other three `enabled: false` (FR-001, FR-003)
- [X] T028 [US3] Style disabled sections in `Sidebar.tsx` with a distinct non-interactive treatment (e.g. reduced opacity, `cursor-not-allowed`, no hover state) and ensure clicking them triggers no navigation, state change, or API call (FR-002, FR-024)
- [X] T029 [US3] Apply the design-token language (rounded selected/active-state indicator, spacious spacing) to `Sidebar.tsx` per contracts/design-tokens.md, keeping it visually consistent with US2's work (FR-014, FR-017)
- [X] T030 [US3] Mount `Sidebar` in `client/src/App.tsx` alongside the map and panel, confirming the map remains full-viewport and interactive with the sidebar present (FR-004)

**Checkpoint**: The full intended navigation structure is visible; only Explore (US1's flow) is
functional, exactly as scoped.

---

## Phase 6: User Story 4 - Use the app comfortably in light or dark theme (Priority: P2)

**Goal**: A user can switch between light and dark theme, with every element in scope re-theming
correctly and the choice persisting.

**Independent Test**: quickstart.md step 5 - toggle theme, confirm every surface including map
chrome re-themes with no illegible text, reload and confirm the choice persisted.

### Implementation for User Story 4

- [X] T031 [US4] Create `client/src/components/ThemeToggle.tsx`: a control using `useTheme()` (T007) to switch `mode`, styled per contracts/design-tokens.md (pill-shaped, `--color-accent` for the active state)
- [X] T032 [US4] Mount `ThemeToggle` in `client/src/App.tsx`'s chrome (e.g. alongside/within the sidebar)
- [X] T033 [US4] Verify MapLibre's own chrome (the `NavigationControl` added in `Map.tsx`, any popups) re-themes correctly in dark mode; since MapLibre controls aren't daisyUI components, add targeted CSS overrides in `client/src/theme/tokens.css` scoped to MapLibre's control class names if the default styling doesn't already respect the token colors (FR-019's "including map chrome")
- [X] T034 [US4] Audit `--color-base-content` / `--color-neutral-content` against their respective `--color-base-100` backgrounds in both `cairns-light` and `cairns-dark` (T004) for readable contrast, adjusting token values if any combination is too low-contrast (FR-022)
- [X] T035 [US4] Toggle to dark theme and sweep every component built in US1-US3 (`TrailPanel`, `TrailOverview`, `PopularityChart`, map markers, `Sidebar`) for any hardcoded color that doesn't resolve through the `cairns-light`/`cairns-dark` tokens (T004) - fix any found. This is SC-004's "zero elements left in the wrong theme's colors" bar, the same role T026 plays for SC-002 in US2

**Checkpoint**: All four user stories are independently functional - full MVP scope complete.

---

## Phase 7: Polish & Cross-Cutting Concerns

**Purpose**: Documentation and final end-to-end validation across all stories

- [X] T036 [P] Update `client/README.md` (or create one if it's still the Vite template default) documenting the new `theme/`/`api/` structure and that `listTrails()` is fixture-backed pending the real trail-listing endpoint (contracts/trail-list-dependency.md)
- [X] T037 Run through `quickstart.md` end-to-end manually (steps 1-6) against the running `client/`+`server/` stack, confirming SC-001-SC-005 from spec.md hold. While running step 2, informally time one click-to-panel interaction against SC-001's "under 10 seconds" target - not a hard pass/fail gate (plan.md treats SC-001 as satisfied structurally by the per-field-loading architecture, not by a measured budget), just a sanity check that the structural argument actually holds in practice

---

## Dependencies & Execution Order

### Phase Dependencies

- **Setup (Phase 1)**: No dependencies
- **Foundational (Phase 2)**: Depends on Setup - BLOCKS all user stories (the theming tokens and
  API layer are load-bearing for every story's UI)
- **User Story 1 (Phase 3)**: Depends on Foundational only
- **User Story 2 (Phase 4)**: Depends on Foundational and directly on US1's components existing
  to style (T012-T020) - implement after US1 even though both are P1
- **User Story 3 (Phase 5)**: Depends on Foundational only - independent of US1/US2's components,
  though it reuses the same design tokens (T004)
- **User Story 4 (Phase 6)**: Depends on Foundational (specifically T006/T007's ThemeProvider) -
  independent of US1/US2/US3's own components
- **Polish (Phase 7)**: Depends on all four user stories being complete

### Within Each Phase

- T004 (tokens) before T005 (import) before T006 (ThemeProvider, which sets `data-theme` the
  tokens must respond to) before T007 (hook)
- T009 (per-trail API functions) before T010/T011 (listTrails, which the fixture and other API
  functions' error-handling convention inform)
- Within US1: T012-T013 (map markers/click) before T017 (App-level state consuming the click
  callback) before T014-T016 (panel/overview/chart components) before T018-T020 (route line,
  dismiss, marker-switch behavior, all of which depend on T017's state existing)

### Parallel Opportunities

- T002, T003 (Setup) in parallel
- T016 (PopularityChart) in parallel with T014-T015 within US1 - different files
- T023, T024 (US2 styling of chart vs. map markers) in parallel - different files
- US3 (Phase 5) and US4 (Phase 6) can be built in parallel with each other once Foundational is
  done, since neither depends on the other's components

---

## Parallel Example: Foundational Phase

```bash
# T002 and T003 (Setup) have no dependency on each other:
Task: "Create client/src/theme/ directory scaffolding"
Task: "Create client/src/api/ directory scaffolding"
```

---

## Implementation Strategy

### MVP First (User Story 1 Only)

1. Complete Phase 1 (Setup) and Phase 2 (Foundational) - the design tokens and API layer are
   required groundwork every subsequent story's components read from directly
2. Complete Phase 3 (User Story 1) - map markers, click-to-open panel, Overview data, route line,
   dismiss behavior
3. **STOP and VALIDATE**: run quickstart.md step 2 against the real running app
4. This alone proves the map-to-panel flow works end-to-end, even before the visual-polish pass

### Incremental Delivery

1. Setup + Foundational → tokens and API layer ready
2. Add US1 → validate independently (functional but not yet fully styled) - MVP
3. Add US2 → validate independently (US1's UI now matches the design language) - the point where
   "clean and slick" actually becomes true, not just "functional"
4. Add US3 → validate independently (sidebar previews the full nav structure)
5. Add US4 → validate independently (light/dark theming works and persists)
6. Polish → docs + full quickstart validation across all four stories together
