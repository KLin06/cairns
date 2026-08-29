# Feature Specification: MVP Frontend Design

**Feature Branch**: `004-mvp-frontend-design`

**Created**: 2026-08-19

**Status**: Draft

**Input**: User description: "A clean, slick, AllTrails-inspired frontend for the trail conditions
app's MVP scope - map browsing plus a trail detail panel, built against what the backend actually
supports today. Neutral slate base with a warm orange/amber accent, pronounced rounded corners
(16-20px+, pill buttons), light and dark theme from the start, desktop-first. Sidebar shows all
four APP_SPEC.md sections (Explore/Saved/Favorited/Plans) but only Explore is functional - the
others are visibly present but disabled. Trail detail panel shows only the Overview section
(info + popularity + route line) - Weather/Conditions and Day-selection are explicitly deferred
since the conditions endpoint isn't implemented yet. Modern grotesk typography, spacious/airy
density, simple accent-colored map markers, thin borders with minimal shadow for elevation."

## User Scenarios & Testing *(mandatory)*

### User Story 1 - Browse trails on the map and open one's overview (Priority: P1)

A visitor lands on the app and sees a full-viewport map of trail markers. They pan/zoom to an
area of interest, click a marker, and a trail detail panel opens showing that trail's name,
difficulty, length, duration, surface composition, feature tags, monthly popularity chart, and
its route drawn on the map. They dismiss the panel and the map is exactly where they left it.

**Why this priority**: This is the entire MVP - without it there is no working app, just a bare
map (today's state) or a design system with nothing to apply it to.

**Independent Test**: Load the app, click any trail marker, confirm the panel opens at full
height immediately (no grow animation) with all Overview fields populated and the route line
visible on the map; click the dismiss control and confirm the map returns to its prior pan/zoom
state with no page reload.

**Acceptance Scenarios**:

1. **Given** the app has loaded, **When** the map finishes loading, **Then** one marker is
   visible for every trail the backend reports as eligible.
2. **Given** the map is showing markers, **When** a user clicks a marker, **Then** a side panel
   docked to the map's edge appears at full height on the first frame (no expand/grow animation),
   and the map remains visible and interactive in the remaining space.
3. **Given** a trail's panel is open, **When** its data has loaded, **Then** the panel shows the
   trail's name, difficulty rating, length, duration, surface type breakdown, feature tags, and a
   12-bar monthly popularity chart, and the trail's route is drawn on the map in the accent color.
4. **Given** a trail's panel is open, **When** the user dismisses it, **Then** the panel closes
   and the map's center/zoom are unchanged from immediately before the marker was clicked.
5. **Given** a trail has no route geometry on record, **When** its panel opens, **Then** every
   other Overview field still displays normally and no route line is drawn - this is not treated
   as an error state.

---

### User Story 2 - Recognize a consistent, polished visual identity (Priority: P1)

Independent of which screen or state a user is looking at, the app should read as one coherent,
deliberately-designed product - not a collection of unstyled or inconsistently-styled parts.

**Why this priority**: This is the actual point of the request - "clean and slick" is a
cross-cutting quality bar for every surface in scope, not a feature of any one screen. A
functionally-complete but visually inconsistent app fails the actual ask.

**Independent Test**: Inspect every interactive/container element visible in the MVP scope
(sidebar, map markers, trail panel, cards, buttons, chips, inputs) and confirm each follows the
same corner-rounding, color, spacing, and typography language rather than a mix of styled and
default-browser-styled elements.

**Acceptance Scenarios**:

1. **Given** any card, button, panel, input, chip, or map marker/popup in the app, **When** it is
   inspected, **Then** it has a rounded corner treatment consistent with the rest of the app - no
   sharp-cornered element sits next to pronounced-rounded ones.
2. **Given** the app in its default state, **When** a user views any screen, **Then** the color
   palette is limited to the defined neutral scale plus the single accent color (used only for
   primary actions, selected/active states, and the route line) - no other hue appears
   incidentally.
3. **Given** the trail panel and its cards, **When** compared against a hypothetical dense/compact
   layout, **Then** they use generous padding and whitespace consistent with an "airy" density,
   not a cramped one.

---

### User Story 3 - See where the rest of the app is headed without it being functional yet (Priority: P2)

A user sees the full intended navigation structure (Explore, Saved, Favorited, Plans) in the
sidebar, so the app doesn't feel like a single-purpose tool, but only Explore actually works.

**Why this priority**: Sets accurate expectations and previews the product's direction without
requiring the accounts/persistence backend this MVP explicitly doesn't build.

**Independent Test**: Load the app and inspect the sidebar; confirm all four sections are visible,
Explore is selected/active by default and navigable, and the other three are visibly non-interactive.

**Acceptance Scenarios**:

1. **Given** the app has loaded, **When** a user looks at the sidebar, **Then** they see four
   labeled sections: Explore, Saved, Favorited, Plans.
2. **Given** the sidebar, **When** a user clicks Saved, Favorited, or Plans, **Then** nothing
   navigates and the disabled visual state (reduced opacity / distinct non-interactive styling)
   makes clear these aren't currently usable, without an error message or dead link.
3. **Given** the sidebar, **When** a user looks at it, **Then** Explore is visibly marked as the
   active/current section.

---

### User Story 4 - Use the app comfortably in light or dark theme (Priority: P2)

A user's system or explicit preference for a dark interface is respected - the app isn't only
usable in one lighting condition.

**Why this priority**: Explicitly requested as in-scope from the start rather than retrofitted;
lower priority than the core browsing flow since a functioning light theme alone still delivers
the MVP's core value.

**Independent Test**: Toggle between light and dark theme and confirm every surface in scope
(sidebar, map chrome, panel, cards, chips, markers/popups) re-themes correctly with no
illegible/low-contrast text or leftover hardcoded colors from the other theme.

**Acceptance Scenarios**:

1. **Given** the app loads with no explicit user preference, **When** it renders, **Then** it
   displays in the light theme by default.
2. **Given** a user switches to dark theme, **When** the switch completes, **Then** every element
   in scope - including the map's own chrome/controls, not just the sidebar and panel - reflects
   dark-theme colors, with body text meeting standard readable contrast against its background in
   both themes.
3. **Given** dark theme is active, **When** the user reloads the app, **Then** their theme choice
   persists rather than resetting to light.

### Edge Cases

- What happens when a trail's popularity data shows zero total reviews? The monthly chart renders
  in its zeroed state (all bars empty/flat) rather than being hidden or showing an error - matches
  the backend's own "empty but present" design for this case.
- What happens when a trail's surface type or feature list is empty/unknown? That part of the
  Overview section is omitted or shown as "not available," not rendered as a broken/empty chip.
- What happens when many trail markers are close together at a given zoom level? Implemented:
  nearby markers merge into a numbered cluster circle (MapLibre's native GeoJSON clustering),
  color/opacity-coded by count so denser clusters read visibly denser, with a stroke ring so two
  separately-clustered groups that end up close together on screen stay legible instead of
  blending together. Clicking a cluster zooms/centers to expand it. A legend explains the
  pin-vs-cluster distinction. Markers remain individually clickable once unclustered at a given
  zoom/viewport.
- What happens if a user clicks a second marker while a panel is already open for a different
  trail? The panel's content updates to the newly-clicked trail without a close/reopen animation
  cycle - it reads as one panel updating, not two panels swapping.
- What happens on a very long trail name or a long list of feature tags? Text wraps or truncates
  gracefully (e.g. with an ellipsis and full text on hover) rather than breaking the card's layout
  or overflowing its rounded container.
- What happens while trail data (info/activity/geometry) is still loading after a marker click?
  The panel appears at full height immediately per User Story 1, with a loading state in place of
  each not-yet-loaded field rather than a blank or jumping layout.

## Requirements *(mandatory)*

### Functional Requirements

**Layout & navigation**

- **FR-001**: The app MUST display a persistent left sidebar with four labeled sections: Explore,
  Saved, Favorited, Plans.
- **FR-002**: Only the Explore section MUST be interactive; Saved, Favorited, and Plans MUST be
  visibly present but MUST NOT navigate anywhere or perform any action when clicked, and MUST be
  visually distinguishable as non-interactive from Explore.
- **FR-003**: Explore MUST be the default active section on load and MUST be visually marked as
  active.
- **FR-004**: The Explore section MUST display a persistent, full-viewport map that remains
  visible and interactive at all times, including while a trail panel is open.

**Map & markers**

- **FR-005**: The map MUST display one marker per trail returned by the app's trail-listing data
  source.
- **FR-006**: Markers MUST use a simple, small accent-colored marker style (dot or pin), not a
  card-style or information-bearing marker.
- **FR-007**: Clicking a marker MUST open the trail detail panel for that trail; clicking a
  different marker while a panel is already open MUST update the same panel to the newly-selected
  trail rather than closing and reopening it.
- **FR-008**: When an open trail has route geometry available, the map MUST render that trail's
  route as a line in the accent color; when unavailable, no route line is drawn and this MUST NOT
  be treated as an error.
- **FR-008a**: Markers that are close together at the current zoom MUST merge into a single
  numbered cluster circle rather than rendering as unreadable overlapping pins; larger clusters
  MUST be visually distinguishable from smaller ones (not uniform regardless of count), and
  clicking a cluster MUST zoom/center the map to expand it. A legend MUST be present explaining
  the single-pin-vs-cluster distinction.
- **FR-008b**: The base map tiles MUST use a muted/desaturated treatment rather than the raw
  default OSM raster style, applied as tile-layer paint properties (not a canvas-wide filter, which
  would also mute the accent-colored cluster/route layers drawn on top). The zoom and compass
  controls MUST be restyled (rounded corners, softened shadow, theme-aware hover) to match the
  rest of the app's visual language rather than using MapLibre's unstyled default chrome.

**Trail detail panel**

- **FR-009**: The trail detail panel MUST be docked to an edge of the map (not a bottom sheet or
  modal overlay) and MUST appear at full height on its first rendered frame - no grow/expand
  animation from a smaller state.
- **FR-010**: Dismissing the panel MUST return the map to exactly the pan/zoom state it was in
  immediately before the panel was opened, without a page reload.
- **FR-011**: The panel MUST contain only an Overview section for this scope - no Weather,
  Conditions, or Day-selection section is included.
- **FR-012**: The Overview section MUST display: trail name, difficulty rating, length, duration,
  surface type breakdown, feature tags, and a monthly (12-bucket) popularity bar chart.
- **FR-013**: While any of a panel's data is still loading, the panel MUST show a loading state
  for the not-yet-available fields rather than leaving the panel blank or shifting layout once
  data arrives.

**Visual design language**

- **FR-014**: Every card, button, input, chip/tag, the trail panel container, and map
  markers/popups MUST use a pronounced rounded-corner treatment (large radius, buttons/chips
  fully pill-shaped where their shape allows) consistently across the app - no element in scope
  may use sharp/unrounded corners.
- **FR-015**: The color system MUST consist of a neutral (slate/gray) base palette plus exactly
  one accent color (warm orange/amber), with the accent reserved for primary actions,
  selected/active states, and the map route line - it MUST NOT appear as incidental decoration.
- **FR-016**: All text MUST render in a single modern grotesk sans-serif typeface family across
  the app, with a defined size/weight scale distinguishing headings, body text, and secondary/meta
  text.
- **FR-017**: Spacing and padding across cards, the panel, and the sidebar MUST follow a
  consistent "spacious" density scale - not a cramped/dense layout.
- **FR-018**: Elevated surfaces (the panel, cards, popups) MUST be visually separated from their
  background using a thin border with minimal or no drop shadow, applied consistently rather than
  mixing border-only and shadow-only treatments across different elements.

**Theming**

- **FR-019**: The app MUST support both a light theme and a dark theme, both fully designed (not
  a partial/inverted-only dark mode), covering every element in scope including map chrome.
- **FR-020**: The app MUST default to the light theme when no prior preference is stored.
- **FR-021**: A user's theme choice MUST persist across reloads within the same browser.
- **FR-022**: In both themes, body text MUST remain clearly readable against its background.

**Scope boundaries**

- **FR-023**: The app MUST NOT include a Weather/Conditions panel section, a date-picker/
  day-selection UI, gear/prep nudges, or a confidence/data-availability indicator in this scope.
- **FR-024**: The app MUST NOT implement any Saved/Favorited/Plans functionality beyond their
  disabled sidebar presence (FR-002) - no saved-trails list, favoriting action, or trip-planning
  UI.
- **FR-025**: The app's layout MUST target desktop/laptop screen sizes; this spec does not require
  a specific mobile or narrow-viewport layout.

### Key Entities

- **Trail marker**: A point on the map representing one backend-eligible trail; carries at least
  a trail identifier and coordinates, sourced from a trail-listing capability this spec assumes
  exists (see Assumptions).
- **Trail overview**: The set of static, non-weather-dependent details about a trail shown in the
  panel - name, difficulty, length, duration, surface composition, feature tags - sourced from the
  existing trail-info data.
- **Trail popularity**: Historical review-count data bucketed by month, shown as the panel's bar
  chart, sourced from the existing trail-activity data.
- **Trail route**: The geographic line(s) representing a trail's path, drawn on the map when
  available, sourced from the existing trail-geometry data.
- **Sidebar section**: One of the four persistent navigation entries (Explore, Saved, Favorited,
  Plans), each with an active/inactive/disabled visual state.
- **Theme**: Light or dark - a named set of color-token values applied consistently across every
  element in scope.

## Success Criteria *(mandatory)*

### Measurable Outcomes

- **SC-001**: A user can go from page load to viewing a specific trail's full Overview details in
  under 10 seconds of interaction (pan/zoom + one click), assuming normal network conditions.
- **SC-002**: 100% of interactive or container elements in scope (sidebar entries, map markers,
  panel, cards, buttons, chips, inputs) visually conform to the app's single rounded-corner,
  color, and typography language - zero elements retain unstyled/default browser appearance.
- **SC-003**: Dismissing and reopening trail panels for different trails never triggers a full
  page reload or loses the map's pan/zoom state, across 100% of tested dismiss/reopen sequences.
- **SC-004**: Every element visible in the MVP scope renders correctly (no illegible text, no
  missing theme colors) in both light and dark theme, with zero elements left in the "wrong"
  theme's colors after a switch.
- **SC-005**: A returning user's theme preference is correctly restored on 100% of subsequent
  visits within the same browser, without needing to re-select it.

## Assumptions

- **A trail-listing capability exists as a dependency, not something this spec builds.** Today the
  backend only supports per-trail-id lookups (`/trails/{id}/info`, `/activity`, `/geometry`); this
  spec assumes a way to enumerate all eligible trails' ids/coordinates for map markers already
  exists or will exist by implementation time. This is the one open item that could block User
  Story 1 outright, and is flagged here rather than as a `[NEEDS CLARIFICATION]` since the fix
  (build that endpoint) is unambiguous and was already identified as the natural next backend step
  in prior work on this project - not a design decision this spec needs to make.
- **Desktop-first, single viewport target.** No responsive/mobile layout is designed or required
  by this spec; the browser window is assumed to be a typical laptop/desktop size.
- **No accounts, no persistence beyond theme preference.** Saved/Favorited/Plans remain
  non-functional placeholders; the only piece of user state this spec requires persisting is the
  light/dark theme choice.
- **Concrete design-token defaults** (chosen here rather than left open, since a design spec
  should be decisive about its own visual language):
  - Typeface: a modern grotesk sans-serif (e.g. Inter or an equivalent) for all text.
  - Corner radius: a small radius (~12px) for inputs, a larger radius (~20px) for cards and
    buttons, full pill shape for chips/tags and standalone action buttons, and a larger radius
    (~24-28px) on the trail panel's map-facing corners only - its outer edge, flush with the
    browser viewport, remains unrounded, matching how docked side panels conventionally behave.
  - Accent color: a single warm amber/orange hue, with light/dark-appropriate variants for
    hover/active states, defined once as a token and reused everywhere the accent appears.
  - Base palette: a neutral slate/gray scale, with separate light-theme and dark-theme token
    values (not a single palette with one color simply inverted), per FR-019.
- **"Loading state" (FR-013, Edge Cases) means a lightweight in-place placeholder** (e.g. a
  skeleton or muted placeholder shape matching the eventual content's size) rather than a
  full-panel spinner - this keeps the "appears at full height immediately" requirement (FR-009)
  intact even before data arrives, but the exact placeholder treatment is an implementation detail
  left to planning, not specified field-by-field here.
