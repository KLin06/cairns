# Phase 0 Research: Saved Trails

No open "NEEDS CLARIFICATION" markers remain in plan.md's Technical Context - the spec's own
Assumptions section already resolved the ambiguous points (toggle edge, default view, row content,
ordering, cross-tab sync, undo). The decisions below cover implementation-approach choices not
already settled by the spec.

## Decision 1: No router library; navigation is lifted `activeView` state

**Decision**: Add a single `activeView: 'explore' | 'saved'` piece of state in `App.tsx` that
picks which main-content component renders (`Map` for explore, `SavedTrailsScreen` for saved). No
`react-router` or similar is added.

**Rationale**: The app currently has zero client-side routing - `App.tsx` is one component tree
with no URL-driven views, and `package.json` has no router dependency. FR-002 requires "real
navigation replacing the current main view (consistent with how the sidebar's other above-the-
trail sections already behave)" - the "already behave" reference is aspirational (those sections
are still disabled placeholders), so there's no existing pattern to match beyond "not an overlay,
not the trail panel." A plain state swap satisfies that literally (the Explore map is fully
replaced, not stacked under/behind anything) with zero new dependencies, matching this app's
consistent "no library for something three lines of state already does" posture (e.g. no state-
management library for `PanelState` in spec 005).

**Alternatives considered**:
- `react-router` with real URL routes (`/`, `/saved`) - would add deep-linking and browser
  back/forward support, but nothing in the spec asks for either, and it's a new dependency plus
  root-level restructuring (`BrowserRouter`, route config) for a two-screen app. Rejected as scope
  the spec doesn't ask for.

## Decision 2: Saved set lives in `App.tsx` state, not a custom hook/context

**Decision**: `App.tsx` holds `const [savedTrails, setSavedTrails] = useState<SavedTrailEntry[]>(...)`,
initialized once from `savedTrails.ts`'s `loadSavedTrails()`, written back to `localStorage` via
`persistSavedTrails()` inside the same setter call that updates state. `TrailOverview` and
`SavedTrailsScreen` both receive the current set (or a derived `isSaved`/list) and a `toggleSaved`
callback as props - the same "lift to `App.tsx`, pass down" shape `panel`/`selectedDate` already
use.

**Rationale**: FR-013 and SC-004 require a save/unsave from either surface (trail panel icon, list
row) to be reflected live in every other currently-open view within the same interaction, with no
reload. A single React state value read by every consumer gets this for free - no pub/sub, no
custom events, no context needed for a two-consumer, single-tab-only requirement (cross-tab sync is
explicitly out of scope per the spec's Assumptions).

**Alternatives considered**:
- React Context provider - adds indirection for exactly two consumer components; `App.tsx` already
  has direct JSX ownership of both, so props are simpler and consistent with the existing
  `panel`-drilling pattern.
- A custom hook (`useSavedTrails()`) instantiated independently in each consuming component,
  backed by a module-level event emitter to keep instances in sync - solves the same problem with
  more moving parts than lifting one `useState` call already solves for free.

## Decision 3: `localStorage` access is wrapped and fails silently

**Decision**: All `localStorage.getItem`/`setItem` calls in `savedTrails.ts` are wrapped in
`try/catch`; a read failure returns an empty list, a write failure is swallowed (in-memory React
state still updates, so saving still works for the rest of that session per the spec's documented
edge case).

**Rationale**: Spec edge case: "What happens if the browser's localStorage is unavailable or
cleared (private/incognito browsing, manual clear)? The saved set reads as empty - no error, no
crash." Safari private mode and storage-quota conditions are the concrete cases where
`localStorage` calls throw synchronously.

**Alternatives considered**: Feature-detecting `localStorage` availability once at module load -
rejected as extra surface for the same outcome; try/catch on each call is simpler and also covers
mid-session failures (e.g. quota hit after several saves), not just unavailability at load.
