# Feature Specification: Saved Trails

**Feature Branch**: `006-saved-trails`

**Created**: 2026-08-29

**Status**: Draft

**Input**: User description: "Add a 'Saved trails' section to the app, consolidating the sidebar's
currently-separate 'Saved' and 'Favorited' placeholder entries into a single 'Saved' entry
(Favorited is removed as its own sidebar item - the sidebar keeps Explore, Saved, Plans). A trail
has one bookmark flag ('saved', also referred to as 'favorited' - the same concept, not two
independent lists), toggled from a new icon added to the trail detail panel's Overview section.
Saved state persists in the browser's localStorage (no backend/database changes, no user accounts
- the app has none today). Clicking the sidebar's Saved entry opens a dedicated saved-trails screen
(not the trail detail panel) with two view modes the user can toggle between: a Map view (the
existing map, but scoped/filtered to only show pins for saved trails) and a List view (a scrollable
list of all saved trails, each row navigable to that trail's normal detail panel). The toggle
between Map/List is a single control, horizontally centered, positioned along the vertical
top-or-bottom edge of the screen (implementer's choice which edge, document the choice as an
assumption). Unsaving a trail (from the list view or from the trail panel's icon) removes it live
from both views without needing to reopen the section. An empty saved list (nothing saved yet)
needs its own clear empty state distinct from a loading or error state, in both view modes."

## User Scenarios & Testing *(mandatory)*

### User Story 1 - Bookmark a trail while looking at it (Priority: P1)

A user has a trail's detail panel open (via the Explore map) and decides it's worth remembering.
They tap a bookmark icon right there in the Overview section, and it visibly flips to "saved" -
no separate screen, no extra steps.

**Why this priority**: This is the entry point for every other story below - nothing can be saved,
listed, or shown on a filtered map until a trail can actually be bookmarked from where the user
already is.

**Independent Test**: Open any trail's detail panel, tap the bookmark icon, close the panel, reopen
the same trail's panel, and confirm the icon still shows "saved" (persisted, not just a transient
UI state).

**Acceptance Scenarios**:

1. **Given** a trail's detail panel is open and it is not currently saved, **When** the user taps
   the bookmark icon, **Then** the icon immediately switches to its "saved" appearance and the
   trail is added to the saved set.
2. **Given** a trail's detail panel is open and it is currently saved, **When** the user taps the
   bookmark icon again, **Then** the icon switches back to its "not saved" appearance and the trail
   is removed from the saved set.
3. **Given** a trail was saved in an earlier session, **When** the user reopens that trail's detail
   panel later (same browser/device), **Then** the bookmark icon already shows "saved" without the
   user having to do anything.

---

### User Story 2 - Browse saved trails as a list (Priority: P2)

A user wants to see everything they've bookmarked, without hunting for pins on the map one at a
time. They click "Saved" in the sidebar and see a simple scrollable list of every trail they've
saved; tapping one takes them straight into that trail's normal detail panel.

**Why this priority**: The list is the simplest, most direct way to answer "what have I saved" and
doesn't depend on the map/list toggle or the map-scoping behavior in User Story 3 to deliver real
value on its own.

**Independent Test**: With at least one trail saved, click the sidebar's Saved entry, confirm the
list view (the default view on entry) shows exactly the saved trails, and confirm tapping a row
opens that trail's detail panel.

**Acceptance Scenarios**:

1. **Given** the user has saved one or more trails, **When** they open the Saved section, **Then**
   every saved trail appears as its own row in the list view.
2. **Given** the saved-trails list is showing, **When** the user taps a row, **Then** that trail's
   normal detail panel opens (the same panel/behavior as clicking its pin on the Explore map).
3. **Given** the saved-trails list is showing, **When** the user unsaves a trail from within this
   screen, **Then** that trail's row disappears from the list immediately, without the user needing
   to leave and reopen the Saved section.

---

### User Story 3 - See saved trails on a map (Priority: P2)

A user wants the spatial picture - which saved trails are near each other, near a place they're
headed, etc. - rather than a flat list. From the Saved section, they flip a toggle to Map view and
see the same map the app already uses elsewhere, but showing only their saved trails' pins.

**Why this priority**: Genuinely useful alongside the list (spatial context the list can't give),
but the Saved section is already functional and valuable via the list alone (User Story 2) - this
is a refinement, not the entry point.

**Independent Test**: With at least one trail saved, open the Saved section, toggle to Map view,
and confirm only saved trails' pins are shown (not every pipelined trail) - then toggle back to
List view and confirm the same set of trails is still there.

**Acceptance Scenarios**:

1. **Given** the user has saved one or more trails, **When** they toggle to Map view, **Then** the
   map shows a pin for each saved trail and no pins for unsaved trails.
2. **Given** the Map view is showing, **When** the user taps a saved trail's pin, **Then** that
   trail's normal detail panel opens.
3. **Given** either view is showing, **When** the user taps the Map/List toggle, **Then** the other
   view renders immediately, still reflecting the same current saved set (no stale data, no reload).

---

### User Story 4 - See a clear empty state before ever saving anything (Priority: P3)

A first-time user (or one who has unsaved everything) opens the Saved section before bookmarking
anything at all. They get a clear message explaining there's nothing saved yet, in whichever view
they land on or switch to - not a blank screen, a loading spinner that never resolves, or something
that reads like an error.

**Why this priority**: A trust/clarity guardrail rather than new capability - lower priority than
the stories that deliver the actual save/browse functionality, but necessary before this ships,
since an empty Saved section is the state every user sees the very first time they click it.

**Independent Test**: With zero trails saved, open the Saved section and confirm a specific "no
saved trails yet" message renders in the default view; toggle to the other view and confirm the
same clear empty state (not a loading spinner or blank map/list) renders there too.

**Acceptance Scenarios**:

1. **Given** the user has never saved a trail, **When** they open the Saved section, **Then** the
   default view shows a specific empty-state message, not a blank list or an empty map with no
   explanation.
2. **Given** zero trails are saved, **When** the user toggles to the other view, **Then** that view
   also shows a specific empty-state message appropriate to itself (e.g., an empty map still reads
   as "nothing to show here yet," not as a loading failure).

---

### Edge Cases

- What happens if a trail the user previously saved is later removed from the app's pipelined trail
  set (e.g., it's dropped from `/trails`)? It simply no longer appears in either saved view - not
  shown as a broken pin or a row with missing data. (Consistent with the existing Pipeline-Gated
  Trail Data principle: only pipelined trails are ever addressable/shown.)
- What happens if the browser's localStorage is unavailable or cleared (private/incognito browsing,
  manual clear)? The saved set reads as empty - no error, no crash. Saving still works for the rest
  of that session; it just won't survive a reload in that case.
- What happens if the user taps the bookmark icon rapidly (save/unsave/save in quick succession)?
  The final state after the taps stop is whatever the last tap left it as - no lost toggles, no
  duplicate entries.
- What happens to the Map/List toggle's own state (which view is showing) when the user navigates
  away from the Saved section and back? It resets to the default view (List) each time the section
  is opened fresh, rather than being remembered as its own persisted setting.

## Requirements *(mandatory)*

### Functional Requirements

**Sidebar**

- **FR-001**: The sidebar MUST present a single "Saved" entry; the previously-separate "Favorited"
  entry MUST be removed. The sidebar's other entries (Explore, Plans) are unaffected.
- **FR-002**: Clicking the sidebar's Saved entry MUST open a dedicated saved-trails screen, as real
  navigation replacing the current main view (consistent with how the sidebar's other
  above-the-trail sections already behave) - not an overlay on top of the Explore map, and not the
  trail detail panel.

**Bookmarking**

- **FR-003**: The trail detail panel's Overview section MUST include a bookmark icon reflecting
  whether that trail is currently saved.
- **FR-004**: Tapping the bookmark icon MUST toggle that trail's saved state immediately, with the
  icon's appearance updating in the same interaction (no separate confirmation step).
- **FR-005**: A trail's saved state MUST persist across page reloads and app restarts on the same
  browser/device.
- **FR-006**: "Saved" is a single flag per trail - the system MUST NOT track "saved" and
  "favorited" as two independent states.

**Saved-trails screen**

- **FR-007**: The saved-trails screen MUST offer exactly two view modes, List and Map, switchable
  via one single toggle control.
- **FR-008**: The toggle control MUST be horizontally centered and positioned along one edge of the
  screen (top or bottom - see Assumptions for which).
- **FR-009**: The List view MUST show every currently-saved trail as its own row.
- **FR-010**: Tapping a row in the List view MUST open that trail's normal detail panel.
- **FR-011**: The Map view MUST show the same map used elsewhere in the app, scoped to render pins
  for only the currently-saved trails - no pins for unsaved trails.
- **FR-012**: Tapping a pin in the Map view MUST open that trail's normal detail panel, the same as
  tapping a pin does on the main Explore map.
- **FR-013**: Unsaving a trail - from the List view's own row, or from the trail detail panel's
  bookmark icon while it's reachable - MUST remove that trail from both the List view and the Map
  view live, without requiring the user to leave and reopen the Saved section.
- **FR-014**: When zero trails are saved, both the List view and the Map view MUST render a
  specific empty-state message distinguishable from a loading state and from an error state.

**Persistence**

- **FR-015**: Saved state MUST be stored client-side (browser localStorage), with no backend or
  database changes and no user-account concept, consistent with the app having neither today.

### Key Entities

- **Saved trail**: One bookmark entry - a trail's id plus when it was saved (used to order the List
  view, most-recently-saved first). Lives entirely in the browser; not synced to any server or
  shared across devices/browsers.

## Success Criteria *(mandatory)*

### Measurable Outcomes

- **SC-001**: A user can save or unsave a trail from its detail panel in a single interaction (one
  tap), with the icon's state updating instantly.
- **SC-002**: 100% of a user's saved trails are still present, correctly, the next time they open
  the app on the same browser/device - saving is never silently lost between sessions absent an
  explicit localStorage clear.
- **SC-003**: A user can switch between the Map and List views of their saved trails in a single
  interaction, with no full-page reload and no visible delay in the switch itself.
- **SC-004**: Unsaving a trail from any reachable surface (list row or trail panel icon) is
  reflected in every other currently-open saved-trails view within that same interaction - never
  requiring a manual refresh to catch up.
- **SC-005**: A user with nothing saved yet is shown a clear explanatory empty state in both view
  modes, on their very first visit to the Saved section - never a blank screen, an endless loading
  indicator, or an error-looking message.

## Assumptions

- **Default view**: The saved-trails screen opens to List view by default (simplest to render
  correctly even at zero saved trails, and doesn't require the map to load first); Map view is
  reached via the toggle. The toggle's own selection is not itself persisted - it resets to List
  each time the section is freshly opened.
- **Toggle placement**: The Map/List toggle is positioned along the bottom edge of the screen,
  horizontally centered (the user's own instruction left top-vs-bottom as an implementer's choice)
  - chosen so it sits within comfortable thumb reach on the narrower viewports this app already
  targets (matching spec 004's mobile-lean layout conventions), without competing with the
  sidebar/header content already anchored at the top.
- **List row content**: Rows show what's already available from the app's existing trail-list data
  (name, and area if present) rather than triggering a full per-trail detail fetch (difficulty,
  surface mix, etc.) just to render the list - keeps opening the Saved section cheap regardless of
  how many trails are saved. Full detail is one tap away via the row itself.
- **Ordering**: The List view orders saved trails most-recently-saved first, since there's no other
  natural ordering (no ratings/relevance signal in scope here).
- **No cross-tab sync**: If the same app is open in two browser tabs, a save/unsave in one tab is
  not required to live-update the other tab's already-rendered view (only the currently-active
  view within a single tab is required to update live, per FR-013). Out of scope for this feature.
- **No undo affordance**: Unsaving is immediate and final (re-saving is always available the same
  way as the original save) - no "undo" toast or confirmation step is in scope.
- **No new sidebar behavior beyond consolidation**: "Plans" remains an existing disabled
  placeholder, unaffected by this feature - only "Favorited" is removed and "Saved" is wired up.
