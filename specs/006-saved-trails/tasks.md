---

description: "Task list for Saved Trails"
---

# Tasks: Saved Trails

**Input**: Design documents from `specs/006-saved-trails/`

**Prerequisites**: plan.md, spec.md, research.md, data-model.md, contracts/saved-trails-storage.md, quickstart.md

**Tests**: Not requested in the feature specification and no client test runner is configured in
this repo (same as spec 005) - verification is manual/browser-based per quickstart.md, folded into
Polish.

## Format: `[ID] [P?] [Story] Description`

## Phase 1: Setup

No new dependencies or project initialization required - this feature adds no runtime
dependencies (research.md decision 1) and touches only existing `client/src/` files. Proceed
directly to Foundational.

---

## Phase 2: Foundational (blocking prerequisites for all user stories)

**Purpose**: The `localStorage` persistence module and the lifted App-level saved-set state every
story reads or mutates.

- [X] T001 [P] Create `client/src/savedTrails.ts`: `SavedTrailEntry` type (`{trailId: string, savedAt: string}`), `loadSavedTrails(): SavedTrailEntry[]` and `persistSavedTrails(entries: SavedTrailEntry[]): void`, exactly per contracts/saved-trails-storage.md's read/write contracts (key `cairns:savedTrails`, try/catch around both `getItem`/`setItem`, drop malformed entries on read, no sort applied - callers sort).
- [X] T002 In `client/src/App.tsx`: add `const [savedTrails, setSavedTrails] = useState<SavedTrailEntry[]>(() => loadSavedTrails())`; add `toggleSaved(trailId: string)` that appends `{trailId, savedAt: new Date().toISOString()}` if not present or removes the matching entry if present, calling `persistSavedTrails` with the new array in the same update (data-model.md's state transitions). (depends on T001)

**Checkpoint**: `savedTrails` state round-trips through `localStorage` across a manual reload (verify via browser devtools before wiring any UI to it).

---

## Phase 3: User Story 1 - Bookmark a trail while looking at it (Priority: P1) 🎯 MVP

**Goal**: A bookmark icon in the trail panel's Overview section toggles and persists a trail's saved state.

**Independent Test**: Open any trail's detail panel, tap the bookmark icon, close the panel, reopen the same trail's panel, confirm the icon still shows "saved."

### Implementation for User Story 1

- [X] T003 [US1] In `client/src/components/TrailOverview.tsx`: add a bookmark icon button to the Overview header area (near the name/area line), accepting new `isSaved: boolean` and `onToggleSave: () => void` props; icon swaps between "not saved" (outline) and "saved" (filled) appearance immediately on click, matching the existing hand-rolled-SVG icon convention already used in this file and in `Sidebar.tsx` (FR-003/FR-004). Only rendered once `state.status === 'ready'`.
- [X] T004 [US1] In `client/src/App.tsx`: pass `isSaved={panel.overview.data ? savedTrails.some(e => e.trailId === panel.overview.data.trailId) : false}` and `onToggleSave={() => panel.overview.data && toggleSaved(panel.overview.data.trailId)}` into `<TrailOverview>`. (depends on T002, T003)

**Checkpoint**: User Story 1 fully functional and independently testable - tap toggles the icon and survives close/reopen and a full page reload (SC-001, SC-002), with no Sidebar/navigation changes needed to verify it.

---

## Phase 4: User Story 2 - Browse saved trails as a list (Priority: P2)

**Goal**: The sidebar's consolidated "Saved" entry opens a dedicated screen showing every saved trail as a row, each navigable to its normal detail panel and each individually unsavable.

**Independent Test**: With at least one trail saved, click the sidebar's Saved entry, confirm the list view (default on entry) shows exactly the saved trails, confirm tapping a row opens that trail's detail panel, confirm unsaving a row removes it live.

### Implementation for User Story 2

- [X] T005 [US2] In `client/src/components/Sidebar.tsx`: remove the `favorited` entry from `SECTIONS` (FR-001), set the `saved` entry's `enabled: true`; add `activeView: 'explore' | 'saved'` and `onSelect: (view: 'explore' | 'saved') => void` props; make the Explore and Saved buttons clickable (`onClick={() => onSelect(section.id)}`, guarded by `section.enabled`); drive `aria-current`/active styling off `activeView === section.id` instead of the current hardcoded `section.id === 'explore'` check.
- [X] T006 [US2] In `client/src/App.tsx`: add `const [activeView, setActiveView] = useState<'explore' | 'saved'>('explore')`; pass `activeView`/`setActiveView` into `<Sidebar>`; in the main content area, render `<SavedTrailsScreen>` in place of `<Map>` when `activeView === 'saved'` (FR-002 - full replacement, not an overlay); keep `<TrailPanel>` rendering on top of whichever main content is active, still driven by `panel.selectedTrailId` regardless of `activeView`. (depends on T005)
- [X] T007 [P] [US2] Create `client/src/components/SavedTrailsScreen.tsx`: accepts `trails: TrailMarker[]`, `savedTrails: SavedTrailEntry[]`, `onToggleSave: (trailId: string) => void`, and `onSelectTrail: (trailId: string) => void` props; derives the saved-trail row list by joining `savedTrails` against `trails` on `trailId`, dropping any `savedTrails` entry with no match in `trails` (Principle VII - a trail dropped from the pipelined set simply doesn't appear), sorted by `savedAt` descending (data-model.md's "Derived views," spec's Ordering assumption); renders a scrollable List view of rows (trail name only - no `areaName` field exists on `TrailMarker`, per plan.md's row-content decision), each row `onClick` calling `onSelectTrail(trailId)` (FR-009/FR-010) and each row carrying its own bookmark/remove icon button calling `onToggleSave(trailId)` directly, without requiring the row to first open the panel (FR-013).
- [X] T008 [US2] Wire `SavedTrailsScreen` into `App.tsx`: pass `trails`, `savedTrails`, `toggleSaved`, and an `onSelectTrail` handler that opens the clicked trail's detail panel the same way a map-pin click does (adapt `handleSelectTrail` - a list row has no "view before select" map state to capture, so pass `panel.mapViewBeforeOpen` through unchanged / `undefined` for that argument rather than reading the (possibly not yet mounted) map's current view). (depends on T002, T006, T007)

**Checkpoint**: User Stories 1 AND 2 both work independently - saved trails show as rows, tapping opens the normal panel, unsaving from a row (or from the still-reachable panel icon) removes it from the list immediately with no reopen (FR-013, SC-004).

---

## Phase 5: User Story 3 - See saved trails on a map (Priority: P2)

**Goal**: A single centered toggle switches the Saved screen between List and the existing map, scoped to only saved trails' pins.

**Independent Test**: With at least one trail saved, open the Saved section, toggle to Map view, confirm only saved trails' pins show, toggle back to List, confirm the same set is still there.

### Implementation for User Story 3

- [X] T009 [US3] In `client/src/components/SavedTrailsScreen.tsx`: add local `const [viewMode, setViewMode] = useState<'list' | 'map'>('list')` (resets to List every time the screen remounts, i.e. every time the Saved section is freshly opened - spec's Assumptions, no persistence needed); add one toggle control, horizontally centered, positioned along the bottom edge of the screen (FR-007/FR-008, plan's chosen edge), switching `viewMode` on click.
- [X] T010 [US3] Same file: when `viewMode === 'map'`, render the existing `Map` component with its `trails` prop set to the joined/filtered saved-trail list from T007 (not the full `trails` array) and `route={null}`; wire `selectedTrailId`/`onSelectTrail` the same way the List view's rows do, so tapping a pin opens the trail's detail panel (FR-011/FR-012). No changes needed to `Map.tsx` itself - it already renders whatever `trails` array it's given. (depends on T007, T009)

**Checkpoint**: All three of US1/US2/US3 independently functional - toggling Map/List is instant with no reload, both views reflect the identical current saved set (FR-011, SC-003).

---

## Phase 6: User Story 4 - See a clear empty state before ever saving anything (Priority: P3)

**Goal**: Zero saved trails renders a specific "nothing saved yet" message in both List and Map view, never a blank/loading-looking screen.

**Independent Test**: With zero trails saved, open the Saved section, confirm a specific empty-state message renders in the default (List) view; toggle to Map view, confirm its own specific empty-state message renders there too.

### Implementation for User Story 4

- [X] T011 [P] [US4] In `client/src/components/SavedTrailsScreen.tsx`: when the joined/filtered saved-trail list (T007) is empty and `viewMode === 'list'`, render a specific "no saved trails yet" empty state in place of the (otherwise-empty) row list (FR-014).
- [X] T012 [US4] Same file: when the joined/filtered list is empty and `viewMode === 'map'`, render a specific empty-state message instead of (or clearly overlaid on) the bare `Map` component, distinguishable from a loading or error look (FR-014). (depends on T009, T010, T011)

**Checkpoint**: All four user stories independently functional - a fresh/emptied saved set reads as an intentional "nothing here yet" in both view modes (SC-005).

---

## Phase 7: Polish & Cross-Cutting Concerns

- [X] T013 [P] Run `tsc -b` and `eslint .` in `client/` - zero new errors/warnings on all changed/new files.
- [X] T014 Browser verification per `quickstart.md`'s US1-US4 flows plus both edge cases (private-browsing `localStorage` failure; a saved `trailId` no longer present in `trails`) using the preview tools; capture a screenshot of the Saved screen in both List and Map view.
- [X] T015 [P] Re-check `SavedTrailsScreen.tsx`'s join logic against constitution Principle VII - confirm a saved id absent from `trails` is silently excluded from both views, never rendered as a broken row or pin.

---

## Dependencies & Execution Order

### Phase Dependencies

- **Setup (Phase 1)**: none - no tasks.
- **Foundational (Phase 2)**: T001 then T002 - BLOCKS all user stories (every story reads/writes `savedTrails` state or the storage module underneath it).
- **User Story 1 (Phase 3)**: depends on Foundational only. Fully independent of Sidebar/navigation - deliverable and testable on its own.
- **User Story 2 (Phase 4)**: depends on Foundational (T002 for `toggleSaved`/`savedTrails`); independent of US1's `TrailOverview` change, though it does reuse the panel-opening logic US1 doesn't touch.
- **User Story 3 (Phase 5)**: depends on US2's T007 (`SavedTrailsScreen` and its joined-list derivation) - adds the map/list toggle on top of it.
- **User Story 4 (Phase 6)**: depends on US2's T007 (empty-list detection) and US3's T009/T010 (`viewMode` to branch the empty-state rendering on).
- **Polish (Phase 7)**: after all four stories are complete.

### Parallel Opportunities

- T001 has no dependencies; T003 (client-only, no dependency on T001/T002's `savedTrails.ts` internals beyond the prop shape) can be drafted in parallel with T001/T002.
- T007 (`SavedTrailsScreen.tsx` creation) can start in parallel with T005 (`Sidebar.tsx`) - different files, both only need T002's `savedTrails`/`toggleSaved` shape to already be decided (not yet merged).
- T011 (List empty state) can be written in parallel with T009/T010 (Map toggle) - different concerns inside the same file, reconciled at T012.
- T013 and T015 in parallel at the end.

## Implementation Strategy

**MVP = User Story 1** (T001-T004): bookmark toggle in the trail panel, persisted to `localStorage`, with zero Sidebar/navigation changes. Stop and validate here before adding the Saved screen.

**Incremental delivery**: Foundational → US1 (MVP, demoable) → US2 (Saved screen + List view, the section's core value) → US3 (Map view toggle) → US4 (empty-state polish) → Polish.
