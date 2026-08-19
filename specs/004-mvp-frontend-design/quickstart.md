# Quickstart: Validate the MVP Frontend Design

Prerequisites: `server/` running (`uvicorn app.main:app --reload` or the `server` launch config)
with the backfilled Postgres data present (`specs/003-trail-storage-backfill`), and `client/`'s
dependencies installed (`npm install` picks up the new `@fontsource-variable/inter` dependency).

## 1. Start both

```bash
cd server && venv/Scripts/python.exe -m uvicorn app.main:app --reload --port 8000
```

```bash
cd client && npm run dev
```

Open the printed local URL (Vite default `http://localhost:5173`).

## 2. Browse and open a trail (User Story 1)

- Confirm the map loads full-viewport with one marker per trail from `listTrails()` (the fixture,
  until the real endpoint exists - see `contracts/trail-list-dependency.md`).
- Click a marker. Expect: the panel appears at full height on the very first frame - no visible
  grow/expand animation - and the map stays visible/interactive beside it.
- With the panel still open, pan and zoom the map. Expect it to respond normally - the open panel
  must not disable or capture map interaction (FR-004).
- Expect the Overview section to show: name, difficulty, length, duration, surface breakdown,
  feature chips, and the 12-bar monthly popularity chart, each appearing as its data loads (a
  loading placeholder before, real content after - not a blank panel then a jump).
- Expect the trail's route to draw on the map in the accent color, if that trail has geometry on
  record; if not, expect no error and no line (Edge Cases).
- Click the panel's dismiss control. Expect the panel to close and the map's pan/zoom to be
  exactly what it was right before the marker click.

## 3. Visual consistency (User Story 2)

- Visually scan the sidebar, map markers, panel, cards, chips, and buttons. Expect every one to
  show the same pronounced rounded-corner language (per `contracts/design-tokens.md`) - no sharp
  corners anywhere except the trail panel's outer viewport-edge (the one documented exception).
- Expect only two hues in use anywhere: the neutral slate scale and the single amber accent (on
  primary actions, the active sidebar item, and the map route line) - no other color.
- Expect generous padding throughout the panel and cards (spacious, not cramped).

## 4. Sidebar preview (User Story 3)

- Expect all four sidebar sections (Explore, Saved, Favorited, Plans) visible on load, Explore
  marked active.
- Click Saved, Favorited, and Plans in turn. Expect each to visibly do nothing (no navigation, no
  error) and to look distinctly non-interactive (e.g. reduced opacity) compared to Explore.

## 5. Theming (User Story 4)

- On first load (no prior visit), expect the light theme.
- Toggle to dark theme. Expect every visible element - including MapLibre's own controls, not just
  the sidebar/panel - to switch, with no leftover light-theme colors and no illegible text.
- Reload the page. Expect dark theme to still be active (persisted via `localStorage`, per
  `data-model.md`'s `Theme` entity).

## 6. Edge cases

- Open a trail with zero total reviews (`totalReviews: 0`). Expect the monthly chart to render in
  its zeroed state (flat/empty bars), not hidden or erroring.
- Open a trail, then click a different marker while its panel is still open. Expect the same panel
  to update to the new trail's data - not a close/reopen animation cycle.
- Resize the browser window to a very narrow width. Confirmed non-goal for this feature (FR-025) -
  don't file layout-breakage below desktop width as a bug against this feature.
