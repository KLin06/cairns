# Quickstart: Validating Saved Trails

## Prerequisites

- Client dev server running: `npm run dev` from `client/` (Vite on :5173).
- Server running on :8000 if you want real trail data (`GET /trails` etc.) - not required to
  exercise the saved/unsaved localStorage mechanics themselves, but needed to see real pins/rows.
- A browser with normal (non-private) storage, plus a private/incognito window for the
  storage-unavailable edge case below.

## US1 - Bookmark a trail from its detail panel

1. Open the app, click any trail pin on the Explore map to open its detail panel.
2. In the Overview section, confirm a bookmark icon is visible, showing "not saved."
3. Tap it - it flips to "saved" immediately (see data-model.md's SavedTrailEntry contract).
4. Close the panel, reopen the same trail - icon still shows "saved" (per contracts/
   saved-trails-storage.md's read contract, backed by `localStorage`).
5. Reload the page entirely, reopen the same trail - icon still shows "saved" (SC-002).
6. Tap again - flips back to "not saved," trail removed from the saved set.

## US2 - Browse saved trails as a list

1. With at least one trail saved (US1), click "Saved" in the sidebar.
2. Confirm the saved-trails screen opens in List view by default, showing exactly the saved
   trail(s) as rows.
3. Tap a row - the trail's normal detail panel opens (same panel as clicking its map pin).
4. From this screen, unsave that trail via the panel's bookmark icon (or, if exposed on the row,
   the row itself) - confirm the row disappears from the list immediately, no reopen needed
   (FR-013).

## US3 - Browse saved trails on a map

1. With at least one trail saved, open the Saved section, toggle to Map view via the centered
   bottom-edge control.
2. Confirm only saved trails' pins render (compare against the Explore map's full pin set for the
   same trails).
3. Tap a pin - the trail's normal detail panel opens.
4. Toggle back to List - same saved set still shown, no reload/flicker (SC-003).

## US4 - Empty state

1. Unsave every trail (or use a fresh browser profile with nothing ever saved).
2. Open the Saved section - List view shows a specific "nothing saved yet" message, not a blank
   list.
3. Toggle to Map view - shows its own specific empty-state message, not a blank/loading map.

## Edge case - `localStorage` unavailable

1. Open the app in a private/incognito window (or a window with storage disabled).
2. Save a trail - the icon still flips to "saved" and the Saved section still shows it for the
   rest of that session (in-memory state, per research.md decision 3).
3. Reload - the saved set is empty again (expected; no crash, no error message).

## Edge case - previously-saved trail dropped from the pipeline

1. (Dev-only check) Save a trail, then manually remove its id from the `/trails` response data (or
   pick a `trailId` in `localStorage` that doesn't exist in the current `trails` table).
2. Reload the Saved section - that trail simply doesn't appear in List or Map view (Principle VII;
   data-model.md's "Derived views" section) - not shown as a broken row/pin.
