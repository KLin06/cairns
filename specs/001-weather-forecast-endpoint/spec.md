# Feature Specification: Trailhead Weather Forecast Endpoint

**Feature Branch**: `001-weather-forecast-endpoint`

**Created**: 2026-08-18

**Status**: Draft

**Input**: User description: "Add an API feature that calls Open-Meteo to return the weather
forecast at a trail's location for the next 14 days, or for a caller-specified date/date range.
Reject dates in the past and dates too far in the future. Distinguish different error types,
including upstream rate limiting."

## Clarifications

### Session 2026-08-18

- Q: Should this endpoint cache a trail's forecast for a short period so repeated requests don't re-call Open-Meteo every time? → A: Short-lived cache per trail (roughly 15–60 min) — repeated requests within that window reuse the last fetch.

## User Scenarios & Testing *(mandatory)*

### User Story 1 - Get the default upcoming forecast for a trail (Priority: P1)

A caller (the trail detail panel's Weather section, or any other API consumer) requests the
weather forecast for a specific trail without specifying any dates, and receives a day-by-day
forecast covering today through the next 14 days at that trail's location.

**Why this priority**: This is the baseline case every other scenario builds on — the
day-by-day weather strip described in APP_SPEC.md's Weather section needs this data to render
at all. Without it, nothing downstream (the date picker, the conditions "why" explanation) has
real data to show.

**Independent Test**: Request the forecast for a trail that has completed the enrichment
pipeline (so its location is known) with no date parameters, and confirm a 14-day, date-sorted
sequence of daily weather records is returned, starting from today.

**Acceptance Scenarios**:

1. **Given** a trail that has a known location, **When** the caller requests its forecast
   without specifying any date, **Then** the response contains one weather record per day for
   today through 14 days from today, in date order.
2. **Given** a trail that has never completed the enrichment pipeline (no known location),
   **When** the caller requests its forecast, **Then** the request is rejected with an error
   that clearly identifies the trail as unavailable, distinct from a forecast-provider failure.

---

### User Story 2 - Get the forecast for a specific date or date range (Priority: P1)

A caller requests the forecast for a single specific date, or an explicit date range, instead
of the default 14-day window — e.g., to check conditions for a trip planned 10 days out, or to
show a shorter window than the default.

**Why this priority**: The date-picker interaction in APP_SPEC.md's "Day selection" section
requires re-fetching or filtering weather for a caller-chosen date, not just the default window
— this is core to the feature being usable for trip planning, not just a fixed preview.

**Independent Test**: Request the forecast for a single valid date within the provider's
available range, and confirm exactly one weather record is returned for that date; request a
valid multi-day range and confirm the full set of days in that range is returned.

**Acceptance Scenarios**:

1. **Given** a trail with a known location, **When** the caller requests the forecast for a
   single valid future date, **Then** the response contains exactly one record for that date.
2. **Given** a trail with a known location, **When** the caller requests the forecast for a
   valid date range, **Then** the response contains one record per day in that range,
   inclusive of both endpoints.

---

### User Story 3 - Rejecting out-of-range date requests (Priority: P2)

A caller requests a forecast for a date that's already passed, or a date too far in the future
for the weather provider to have any real forecast data for, and receives a clear rejection
rather than a fabricated or silently-adjusted answer.

**Why this priority**: Per the project constitution's forecast-horizon principle, a confidently
wrong or silently truncated answer is worse than an explicit rejection — this directly protects
the trustworthiness of every other feature (like predicted trail conditions) that depends on
this endpoint's data being real, not guessed.

**Independent Test**: Request a date before today, and separately a date well beyond the
provider's forecast horizon, and confirm both are rejected with an error that explains the
valid date range, without returning any weather data.

**Acceptance Scenarios**:

1. **Given** a trail with a known location, **When** the caller requests a forecast for a date
   before today, **Then** the request is rejected with an error stating the date is in the past.
2. **Given** a trail with a known location, **When** the caller requests a forecast for a date
   beyond the provider's forecast horizon, **Then** the request is rejected with an error
   stating the date is too far out, and the valid range is communicated back to the caller.
3. **Given** a caller-specified date range where only part of the range falls outside the valid
   window, **When** the request is made, **Then** the entire request is rejected (no partial /
   silently-truncated response) with an error identifying which part of the range is invalid.

---

### User Story 4 - Distinguishing a bad request from a provider outage (Priority: P2)

When something goes wrong, a caller (or a developer debugging the integration) can tell whether
the problem was with their own request (e.g., an invalid date) or with the upstream weather
provider being temporarily unavailable or rate-limiting requests, so they know whether to
change their request or simply retry later.

**Why this priority**: Without this distinction, every failure looks the same to a caller,
which makes the "reject don't degrade" behavior from User Story 3 indistinguishable from a
transient outage — undermining trust in every rejection the endpoint returns.

**Independent Test**: Simulate an upstream rate-limit response from the weather provider after
retries are exhausted, and confirm the caller receives an error distinct in kind from a bad
date-range error, and that it indicates the failure is transient/upstream rather than a problem
with the request itself.

**Acceptance Scenarios**:

1. **Given** a valid request, **When** the upstream weather provider is rate-limiting requests
   and retries are exhausted, **Then** the caller receives an error indicating a transient
   upstream failure, not a request-validation error.
2. **Given** a valid request, **When** the upstream weather provider fails for a reason other
   than rate limiting, **Then** the caller receives an error indicating an upstream failure,
   distinguishable from both a request-validation error and a rate-limit-specific error.

### Edge Cases

- What happens when the requested date range spans both valid and invalid dates (e.g., start
  date valid, end date beyond the horizon)? Covered by User Story 3, Scenario 3 — the whole
  request is rejected, not partially served.
- What happens when the trail ID doesn't correspond to any trail at all (not just "not yet
  enriched," but nonexistent)? Treated identically to "location unknown" (User Story 1,
  Scenario 2) from the caller's perspective — this endpoint has no way to distinguish "never
  existed" from "not yet enriched."
- What happens if the weather provider returns data for some but not all requested days (a
  partial upstream response)? Treated as an upstream failure (User Story 4) — the caller must
  not receive a response that looks complete but silently has missing days.
- What happens on a request for "today" specifically — is that a valid, non-past date? Yes;
  today is the earliest valid date, not treated as "in the past."

## Requirements *(mandatory)*

### Functional Requirements

- **FR-001**: System MUST return a day-by-day weather forecast for a given trail's location
  when no date is specified, covering today through 14 days from today.
- **FR-002**: System MUST allow a caller to request the forecast for a single specific date
  instead of the default window.
- **FR-003**: System MUST allow a caller to request the forecast for an explicit date range
  instead of the default window.
- **FR-004**: System MUST reject any request (whole request, not just the offending date) where
  any requested date falls before today.
- **FR-005**: System MUST reject any request where any requested date falls beyond the weather
  provider's real forecast horizon, rather than truncating the response or estimating data for
  those days.
- **FR-006**: System MUST communicate the valid date range back to the caller whenever a
  request is rejected for being out of range, so the caller can correct and retry.
- **FR-007**: System MUST determine a trail's location from that trail's existing enrichment
  data, and MUST reject the request with a clear "trail unavailable" error (not a generic
  failure) if that trail has no location on record.
- **FR-008**: System MUST distinguish, in the error returned to the caller, between: (a) a
  problem with the request itself (invalid/out-of-range dates, unknown trail), and (b) a
  problem reaching or receiving valid data from the upstream weather provider.
- **FR-009**: System MUST further distinguish upstream failures caused by the weather
  provider rate-limiting requests from other kinds of upstream failure, so a caller can tell a
  transient, retry-worthy failure from other errors.
- **FR-010**: System MUST NOT return a response that presents partial or estimated data as if
  it were a complete, real forecast.
- **FR-011**: System MUST reuse a trail's already-fetched forecast for a short period (roughly
  15–60 minutes) instead of re-calling the weather provider for every request covering the same
  trail and date window within that period.

### Key Entities

- **Forecast request**: identifies a trail and either an implicit default window (today +14
  days) or a caller-specified single date / date range.
- **Daily weather record**: one day's forecasted conditions (temperature range, precipitation,
  wind, snow) at a trail's location.
- **Trail location**: latitude/longitude associated with a trail, sourced from that trail's
  existing enrichment data — this feature does not compute or collect it.

## Success Criteria *(mandatory)*

### Measurable Outcomes

- **SC-001**: A caller can retrieve the default 14-day forecast for any fully-enriched trail in
  a single request.
- **SC-002**: 100% of requests for dates outside the valid window (past, or beyond the
  provider's real horizon) are rejected with no weather data returned — zero instances of
  fabricated, estimated, or silently truncated forecasts reaching a caller.
- **SC-003**: A caller can determine, from the error alone, whether a rejected request was
  their own mistake (bad date/unknown trail) versus a temporary problem with the upstream
  weather provider, without needing to inspect logs or contact a developer.
- **SC-004**: A caller can distinguish a rate-limit-caused upstream failure from any other kind
  of upstream failure, from the error response alone.
- **SC-005**: Repeated requests for the same trail and date window within a short period (roughly
  15–60 minutes) result in at most one upstream weather-provider call, not one per request.

## Assumptions

- "Today" is determined by server time at the moment of the request, not the caller's local
  time zone.
- The weather provider's real forecast horizon is treated as the authoritative outer boundary
  for "too far in the future," rather than a fixed independent business rule — if the provider's
  actual available horizon differs from 14 days, the boundary follows the provider's real
  capability (this is why the default window and the maximum valid window are different: 14
  days is the convenient default, not the hard limit).
- A trail that exists but hasn't completed the scrape/clean/enrich pipeline (per the project
  constitution's Pipeline-Gated Trail Data principle) has no queryable location, and is treated
  the same as an unknown trail for this endpoint's purposes — this endpoint does not trigger
  on-demand enrichment.
- This endpoint returns the provider's forecast data as-is (temperature, precipitation, wind,
  snow) and does not compute or return any derived trail-condition predictions — that remains
  the separate conditions capability, per the project constitution's endpoint-separation
  principle.
- Upstream rate-limiting is expected to be handled with retries before being treated as a
  failure at all; only exhausted retries surface as a rate-limit error to the caller.
