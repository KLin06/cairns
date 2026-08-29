# Feature Specification: Weather & Predicted Conditions UI

**Feature Branch**: `005-weather-conditions-ui`

**Created**: 2026-08-29

**Status**: Draft

**Input**: User description: "Implement the weather UI and the trail-conditions ML prediction
model, end to end (backend + frontend), building on what already exists: the forecast endpoint is
live, the conditions endpoint/schema exist but the service is a stub, and the trail panel only has
its Overview section so far, with Weather/Day-selection explicitly deferred from spec 004 pending
this. Use the currently trained model as-is - no retraining or model-quality work in scope."

## User Scenarios & Testing *(mandatory)*

### User Story 1 - See predicted conditions for a chosen day (Priority: P1)

A user has a trail's Overview panel open and wants to know what the trail will actually be like on
a specific day: is it likely to be muddy, icy, buggy? They pick a day within the next ~16 days and
see that day's raw weather (temperature, precipitation, wind, snow) side-by-side with the model's
per-condition predictions (bugs, flooded, icy, muddy, slippery, snow), each with a probability, a
plain-language flag, a note on how much historical data backs that trail's prediction, and a
concrete prep suggestion for anything flagged.

**Why this priority**: This is the feature's entire reason for existing - "will this trail be
muddy on Saturday" is the core question the app was built to answer (per APP_SPEC.md's problem
statement) and everything else (best-days chart, day-of-week overlay) is a refinement on top of it.

**Independent Test**: Open a trail's panel, scroll to the Weather section, select a day inside the
forecast window, and confirm that day's raw weather and predicted conditions (each with a
probability, a flag, a confidence note, and prep guidance where flagged) render together without
a full-page reload or losing panel scroll position.

**Acceptance Scenarios**:

1. **Given** a trail's panel is open, **When** the user scrolls to the Weather section with no day
   explicitly selected yet, **Then** it defaults to today and shows today's weather and predicted
   conditions.
2. **Given** the Weather section is showing a selected day, **When** the user picks a different day
   within the forecast window, **Then** both the raw weather and the predicted conditions update to
   that day without a page reload, and any other panel surface sharing the selected date (see User
   Story 2) updates to match.
3. **Given** a day's conditions have loaded, **When** any condition's predicted probability meets
   that condition's own flagged threshold, **Then** it is visually marked as flagged (not just
   listed with a number) and paired with a concrete prep suggestion (e.g. icy → "microspikes
   recommended," muddy → "waterproof boots," buggy → "bring repellent").
4. **Given** a day's conditions have loaded, **When** the user views the predicted-conditions
   display, **Then** a data-availability signal is shown alongside it (e.g. "based on 975
   historical reports for this trail," or an explicit "limited data" flag for a thin-review trail) -
   never a bare probability with no context.
5. **Given** a trail has very few historical reviews, **When** its predicted conditions are shown,
   **Then** the "limited data" signal is shown instead of a false sense of confidence, but the
   prediction itself still renders (this is a trust signal, not a block).

---

### User Story 2 - Find the best day to go within the forecast window (Priority: P2)

A user isn't fixed on one date - they want to know which of the next ~16 days is the best bet for
good conditions, and would like to avoid the busiest days if a similarly-good quieter day exists.
They see a strip of the next ~16 days, each colored by how favorable its predicted conditions are
and annotated with how busy that day of week historically runs, and picking a day here drives the
same selected day used in the Weather section.

**Why this priority**: Genuinely useful trip-planning value on top of User Story 1, but the app is
still functional and answers the core question without it - a user can already get a specific
day's answer by picking dates one at a time in the Weather section.

**Independent Test**: Scroll to the Day Selection section, confirm a ~16-day strip renders colored
by conditions favorability with day-of-week popularity visible on the same strip (not a separate
chart), tap a day, and confirm the Weather section above updates to that day.

**Acceptance Scenarios**:

1. **Given** the Day Selection section has loaded, **When** it renders, **Then** it shows a
   horizontal strip covering today through the end of the forecast window, each day colored by its
   own predicted-conditions favorability.
2. **Given** the same strip, **When** it renders, **Then** each day's historical day-of-week
   popularity is layered onto that same strip (e.g. a busy-ness indicator per pill) rather than
   presented as its own standalone chart.
3. **Given** the strip is visible, **When** the user taps a day pill, **Then** the shared selected
   date updates and the Weather section (User Story 1) reflects the new day without the user losing
   their scroll position in the panel.
4. **Given** the strip is visible, **When** the user has already selected a day elsewhere (e.g. the
   Weather section's own date control), **Then** the same day is already highlighted here - the
   strip never shows a stale or independent selection.

---

### User Story 3 - Get a clear answer at the edges of what the app can predict (Priority: P3)

A user tries to check conditions for a date beyond the ~16-day forecast horizon, or for a trail the
weather provider or model can't currently produce a result for. They get a clear, specific message
about why, not a silently wrong guess or a generic error.

**Why this priority**: Correctness/trust-preserving guardrail rather than new capability - lower
priority than the two stories that deliver the actual feature, but a MUST per the constitution
(honest uncertainty, hard forecast-horizon boundary) before this ships broadly.

**Independent Test**: Request conditions for a date past the forecast horizon and confirm a
specific "outside forecast range" message with the valid range is shown instead of a blank panel,
a generic error, or a value that looks like a real prediction.

**Acceptance Scenarios**:

1. **Given** a user is on the Day Selection strip, **When** they attempt to select a date beyond the
   forecast horizon, **Then** that date is not selectable (rendered as clearly disabled), consistent
   with the `/weather` endpoint's own already-enforced range.
2. **Given** a trail has no location on record or hasn't been through the enrichment pipeline,
   **When** its Weather section attempts to load, **Then** a specific "not available for this
   trail" message is shown, distinct from a generic loading-failed error.
3. **Given** the weather provider is unreachable or rate-limited, **When** the Weather section
   attempts to load, **Then** a specific "conditions temporarily unavailable, try again shortly"
   message is shown, distinct from "not available for this trail."

---

### Edge Cases

- What happens when a condition's model has too few positive examples to have been trained at all
  (e.g. `dusty`, excluded per `MODEL_NOTES.md`)? That condition MUST simply be absent from the
  predicted-conditions display, not shown as 0% (0% implies "trained and predicted unlikely," which
  is a different, false claim).
- What happens the first time a user opens the Weather section and the forecast/conditions
  requests are both still in flight? Both the raw-weather and predicted-conditions areas show their
  own independent loading state (matching spec 004's per-field loading convention), not a single
  all-or-nothing spinner for the whole section.
- What happens if the user rapidly taps through several days on the strip before earlier requests
  resolve? Only the latest-selected day's response is rendered when it arrives; a stale response for
  a since-abandoned day selection MUST NOT overwrite what's currently displayed.
- What happens on a trail with a valid location but literally zero historical reviews (activity
  totalReviews = 0)? The "limited/no data" signal is shown and predictions still render if the model
  can produce them (the model doesn't require review history for a *specific* trail beyond what it
  was trained on) - this is distinct from a trail that's missing entirely from the pipeline (User
  Story 3, Scenario 2).

## Requirements *(mandatory)*

### Functional Requirements

**Backend: conditions prediction**

- **FR-001**: The system MUST implement `GET /trails/{trail_id}/conditions` (currently a stub)
  to return real model-backed predictions using the already-trained model artifact, for a single
  requested date.
- **FR-002**: For each condition the model was trained on, the response MUST include a probability
  and a boolean flagged/predicted value derived from that condition's own tuned threshold - never a
  single blanket threshold applied to every condition.
- **FR-003**: A condition excluded from training (insufficient positive examples) MUST be omitted
  from the response entirely, not represented as a low/zero probability.
- **FR-004**: The live feature-assembly step that builds a model input row at request time MUST
  produce a column-for-column identical structure (same columns, order, dtypes, categorical
  handling) to the offline training-table builder, implemented as one shared piece of logic used by
  both, per the constitution's Feature Parity principle - not reimplemented separately for
  inference.
- **FR-005**: Requests for a date beyond the forecast provider's horizon (matching the existing
  `/weather` endpoint's own enforced range) MUST be rejected with a specific, actionable error
  identifying the valid range - never a silent estimate or seasonal-average fallback.
- **FR-006**: The conditions endpoint MUST remain a distinct code path from the trail-info (static)
  endpoint - it MUST NOT be merged into a single computation or handler, per the constitution's
  Endpoint Separation principle.
- **FR-007**: The response MUST include a per-trail confidence/data-availability signal (e.g. the
  historical review count backing that trail, or an explicit "limited data" indicator for
  thin-review trails) accompanying every prediction - a probability MUST NOT be returned without it.
- **FR-008**: When the weather provider is unreachable or rate-limited, or the requested trail has
  no location on record, the endpoint MUST return a specific, distinguishable error for each case
  (matching the existing `/weather` endpoint's error-type convention) rather than a generic failure.

**Frontend: Weather section**

- **FR-009**: The trail detail panel MUST gain a Weather section (per spec 004's deferred scope),
  appearing after Overview and after Day Selection in the panel's single continuous scroll (revised
  post-implementation: pick the day on the Day Selection strip first, then see that day's detail
  below it) - not a separate tab or route.
- **FR-010**: The Weather section MUST display, for the currently selected date: raw daily weather
  (temperature high/low, precipitation, wind, snow) and the model's per-condition predictions,
  together in the same section - the raw numbers are what make a flagged condition's "why"
  checkable rather than a black box.
- **FR-011**: Any condition whose predicted probability meets its flagged threshold MUST be shown
  with a concrete, condition-specific prep suggestion, not just a number.
- **FR-012**: The confidence/data-availability signal returned by the backend (FR-007) MUST be
  displayed alongside the predicted conditions, not buried or omitted client-side.
- **FR-013**: The Weather section's raw-weather and predicted-conditions areas MUST each show their
  own independent loading state, matching the existing per-field loading convention already used in
  the Overview section.

**Frontend: Day selection**

- **FR-014**: The trail detail panel MUST gain a Day Selection section containing a ~16-day
  horizontal date-strip picker and a best-days chart, appearing after Overview and before the
  Weather section in the same continuous scroll (revised post-implementation - see FR-009).
- **FR-015**: The selected date MUST be a single piece of shared state read and written by the
  Weather section, the date-strip picker, and the best-days chart - selecting a date in any one of
  them MUST update the other two, per the constitution's Shared Date State principle.
- **FR-016**: The best-days chart MUST color/rank each of the next ~16 days by its own predicted
  conditions favorability.
- **FR-017**: Historical day-of-week popularity MUST be layered onto the best-days chart's existing
  per-day strip (not rendered as its own standalone chart), per the constitution's Popularity
  Granularity Honesty principle.
- **FR-018**: Dates beyond the forecast horizon MUST be rendered as disabled/non-selectable on the
  date-strip, consistent with the backend's own enforced range (FR-005).
- **FR-019**: Selecting a date via any of the three surfaces MUST NOT reset the user's scroll
  position within the panel or read as a navigation/page change.

**Cross-cutting**

- **FR-020**: A stale response for a day the user has since navigated away from (by picking a
  different day before the first request resolved) MUST NOT overwrite the currently-displayed
  selected day's content.
- **FR-021**: The Weather and Day Selection sections MUST reuse this app's existing design tokens
  (color, radius, typography scale) and card conventions established in spec 004 - no new visual
  language introduced for this feature.

### Key Entities

- **Conditions prediction**: One trail + one date's model output - a probability and a
  flagged/predicted boolean per trained condition, plus the confidence/data-availability signal for
  that trail. Distinct from a **Daily weather record** (one trail + one date's raw forecast values:
  temp high/low, precip, wind, snow), which the prediction is derived from but which also stands on
  its own as the section's "raw" half.
- **Selected date**: Panel-level shared UI state - the single date driving what the Weather section
  and the Day Selection section's date-strip/best-days chart currently display. Bounded to the
  forecast provider's horizon (today through today+~15).
- **Gear/prep suggestion**: A fixed condition → suggestion mapping (e.g. icy → microspikes, muddy →
  waterproof boots, buggy → repellent) shown alongside any flagged condition.
- **Best-day entry**: One of the ~16 days in the date-strip/best-days chart - carries that day's
  conditions-favorability ranking and its historical day-of-week popularity, both layered onto the
  same per-day pill.

## Success Criteria *(mandatory)*

### Measurable Outcomes

- **SC-001**: A user can go from opening a trail's panel to seeing that day's predicted conditions
  for a self-chosen date within the forecast window without any full-page reload or navigation.
- **SC-002**: 100% of predicted-conditions displays shown to a user include an accompanying
  confidence/data-availability signal - never a bare probability.
- **SC-003**: Selecting a date in any one of the three date-aware surfaces (Weather section,
  date-strip picker, best-days chart) is reflected in the other two on the same interaction, with
  no case of the three disagreeing about the currently selected date.
- **SC-004**: 100% of requests for a date beyond the forecast horizon receive a specific,
  actionable message naming the valid range, rather than a value that could be mistaken for a real
  prediction.
- **SC-005**: A condition the model was not trained to predict (e.g. `dusty`) never appears in the
  predicted-conditions display for any trail.

## Assumptions

- The currently trained model artifact (`data/datasets/models/condition_models.joblib`) is used
  as-is; retraining, feature-engineering changes, or model-quality improvements (see
  `MODEL_NOTES.md`'s "Recommended next improvements") are explicitly out of scope for this feature.
- The confidence/data-availability signal is sourced from the trail's existing historical review
  count (already available via the activity endpoint) with a reasonable low-data cutoff (e.g. under
  ~20 historical reviews reads as "limited data") - the exact cutoff is a tuning detail, not a
  product decision requiring sign-off, and can be adjusted during implementation without a spec
  change.
- The condition → gear/prep suggestion mapping is a fixed, hardcoded lookup (one suggestion per
  condition), not a configurable or backend-driven list, consistent with how small and stable this
  set is (six trained conditions).
- "Predicted conditions favorability" for the best-days chart is a simple derived ranking (e.g.
  fewest/least-severe flagged conditions ranks best) rather than a separately-trained composite
  score - no new model output is introduced for this ranking.
- This feature does not change anything about the map, clustering, or the Overview section's
  existing content/styling (spec 004) - it only adds the two sections spec 004 explicitly deferred.
- Both new panel sections are covered by the same light/dark theme and design-token system as the
  rest of the panel (spec 004); no new color, radius, or typography values are introduced.
