# Feature Specification: Trail Data Storage Schema

**Feature Branch**: `002-trail-data-storage-schema`

**Created**: 2026-08-18

**Status**: Draft

**Input**: User description: "Add a persistent data storage layer for trail data, backing the
frontend-facing trail information the app already serves. Store only the processed fields the
frontend actually displays (trail info, activity aggregates, route geometry, map location) —
not raw pipeline output, not weather-dependent or model-inference data. This spec defines the
storage schema only, not the backfill process or the service migration to use it."

## Clarifications

### Session 2026-08-18

- Q: Can a trail's popularity aggregate and route geometry be refreshed independently of its overview record (and of each other), or must all three always be written together as one atomic update? → A: Independent — each of the three can be refreshed on its own schedule, independent of the others; one freshness timestamp per entity type.

## User Scenarios & Testing *(mandatory)*

### User Story 1 - Trail overview and detail info is available from storage (Priority: P1)

A backend request for a trail's static overview information (name, difficulty, length,
duration, whether it has scrambling, surface composition, terrain characteristics, feature
tags) can be satisfied by reading a stored, structured record for that trail — the same
information the trail detail panel's Overview section already displays, per APP_SPEC.md.

**Why this priority**: This is the core static content every trail detail view depends on; it's
also the first thing shown when a trail is opened (per APP_SPEC.md, before Weather/Day
selection load), so it has to exist in a well-defined, queryable shape before anything else
built on top of it makes sense.

**Independent Test**: Store a representative trail record covering every field in this
scenario, then confirm all of them can be read back correctly, including the irregularly-shaped
ones (surface composition list, feature tag list).

**Acceptance Scenarios**:

1. **Given** a trail that has completed the full scrape/clean/enrich pipeline, **When** its
   record is stored, **Then** its name, difficulty rating, length, duration, scrambling flag,
   surface composition, terrain characteristics, and feature tags are all retrievable exactly
   as stored.
2. **Given** a trail that has not completed the full pipeline, **When** storage is populated,
   **Then** that trail has no record in storage at all — partial or unenriched trails are never
   stored.

---

### User Story 2 - Trail popularity aggregates are available from storage (Priority: P2)

A backend request for a trail's popularity information (review counts by month, review counts
by day of week, total review count) can be satisfied by reading a stored aggregate for that
trail — the same rollup the trail detail panel's popularity chart and best-days strip already
use.

**Why this priority**: This is a real but secondary feature relative to core trail info — it
enriches the detail view but isn't the first thing a user needs to see a trail at all.

**Independent Test**: Store a representative activity aggregate for a trail, then confirm the
monthly counts, day-of-week counts, and total count are all retrievable exactly as stored,
without needing to re-derive them from anything else.

**Acceptance Scenarios**:

1. **Given** a trail with historical review data, **When** its popularity aggregate is stored,
   **Then** its by-month counts, by-day-of-week counts, and total review count are all
   retrievable exactly as stored.
2. **Given** a trail with no historical reviews at all, **When** its popularity aggregate is
   stored, **Then** it's retrievable as an empty/zero aggregate rather than being absent or
   causing an error.

---

### User Story 3 - Trail route geometry is available from storage (Priority: P2)

A backend request for a trail's route geometry (the line/path shape used to draw the trail on
the map) can be satisfied by reading a stored geometry record for that trail.

**Why this priority**: Needed for the map-based route rendering described in APP_SPEC.md, but
only relevant once a trail is already selected — later in the user's flow than overview info.

**Independent Test**: Store a representative route geometry for a trail (a multi-point path),
then confirm the exact coordinate sequence is retrievable unchanged.

**Acceptance Scenarios**:

1. **Given** a trail with known route geometry, **When** it's stored, **Then** the full
   coordinate sequence is retrievable exactly as stored, preserving point order.
2. **Given** a trail with no route geometry on record, **When** storage is populated, **Then**
   that trail simply has no geometry record — it does not block storing that trail's other
   information (overview info, activity aggregate).

---

### User Story 4 - Trail identity and location is available for map display (Priority: P1)

A backend request for the set of trails to show as markers on the map (trail identity and
coordinates) can be satisfied by reading stored location records, without needing to open every
trail's full detail record just to place a pin.

**Why this priority**: This is the entry point into the whole app per APP_SPEC.md's "Trail
discovery" section — the map is the default view, populated before any single trail is opened.

**Independent Test**: Store location records for multiple trails, then confirm each trail's
identity and coordinates can be retrieved individually or as a set, independent of retrieving
any trail's full overview/activity/geometry data.

**Acceptance Scenarios**:

1. **Given** multiple trails that have completed the pipeline, **When** their records are
   stored, **Then** each trail's identity and coordinates can be retrieved without also loading
   that trail's full overview, activity, or geometry data.

### Edge Cases

- What happens when a field that used to have a value now has none (e.g. a trail with unknown
  terrain characteristics because it falls outside soil-survey coverage)? The field is stored as
  genuinely absent/unknown, not defaulted to a misleading placeholder value.
- What happens if a trail is later re-enriched with updated data? Out of scope for this spec —
  covered by the separate backfill/sync spec — but the schema itself must not prevent an
  existing trail's stored record from being safely replaced later.
- What happens to a trail's other stored data (activity, geometry) if its overview info is
  somehow missing? Not a real case in practice — Principle VII means a trail is only stored at
  all once it has completed the full pipeline, so overview info is always present for any
  trail with any other stored data.

## Requirements *(mandatory)*

### Functional Requirements

- **FR-001**: Storage MUST hold, per trail, exactly the fields the frontend's trail overview
  display uses: name, difficulty rating, length, duration, a scrambling flag, surface
  composition (a list of surface type / percentage pairs), terrain characteristics (rock slip
  risk, soil drainage), and feature tags — and no other fields from that trail's source pipeline
  data.
- **FR-002**: Storage MUST hold, per trail, exactly the fields the frontend's popularity display
  uses: review counts by month, review counts by day of week, and total review count — as a
  precomputed aggregate, not raw per-review records.
- **FR-003**: Storage MUST hold, per trail, its route geometry as an ordered coordinate
  sequence, when that trail has route geometry on record.
- **FR-004**: Storage MUST hold, per trail, its identity (a stable trail identifier and name)
  and map coordinates, independently retrievable without loading that trail's overview,
  activity, or geometry data.
- **FR-005**: Storage MUST NOT contain a trail record for any trail that has not completed the
  full scrape/clean/enrich pipeline.
- **FR-006**: Storage MUST NOT contain any field, from any pipeline stage, that isn't one of the
  fields enumerated in FR-001 through FR-004 above.
- **FR-007**: Fields with a fixed, predictable shape (name, difficulty rating, length, duration,
  scrambling flag, terrain characteristics, latitude/longitude, total review count) MUST be
  stored as individually addressable fields, not bundled inside an irregularly-shaped blob.
- **FR-008**: Fields that are inherently list-shaped or variable in size (surface composition,
  feature tags, monthly/day-of-week count breakdowns, route coordinate sequences) MAY be stored
  as a single structured value per trail, rather than requiring one row per list item.
- **FR-009**: A field with no known value for a given trail MUST be retrievable as genuinely
  absent/unknown, distinguishable from a zero or empty value.
- **FR-010**: Storage MUST record when each trail's data was last written, so a future
  freshness/re-sync check can tell how old a stored record is without needing to compare
  against the source pipeline files directly.
- **FR-011**: The overview record, popularity aggregate, and route geometry for a given trail
  MUST be independently refreshable — updating one MUST NOT require rewriting the others, and
  each MUST carry its own last-written timestamp rather than sharing one freshness signal for
  the whole trail.

### Key Entities

Each entity below is independently refreshable and carries its own last-written timestamp
(FR-010, FR-011) — updating one never requires rewriting another.

- **Trail overview record**: One per trail — identity, location, difficulty/length/duration,
  scrambling flag, surface composition, terrain characteristics, feature tags, and its own
  last-written timestamp.
- **Trail popularity aggregate**: One per trail — monthly review counts, day-of-week review
  counts, total review count, and its own last-written timestamp. Logically tied to a trail
  overview record but represents a distinct kind of data (rollup of behavior over time, not
  trail attributes) with its own refresh cadence.
- **Trail route geometry**: One per trail (when available) — an ordered sequence of
  coordinates, and its own last-written timestamp. Logically tied to a trail overview record but
  independently optional and independently refreshable.

## Success Criteria *(mandatory)*

### Measurable Outcomes

- **SC-001**: Every field currently shown in the trail detail panel's Overview section can be
  read from storage for any fully-enriched trail, with no data loss compared to that trail's
  source pipeline output.
- **SC-002**: Map marker data (trail identity + coordinates) for any number of trails can be
  retrieved without incurring the cost of loading every trail's full detail data.
- **SC-003**: Zero trails that haven't completed the full pipeline ever appear in storage.
- **SC-004**: Zero fields outside the enumerated set (FR-001–FR-004) ever appear in storage,
  verifiable by inspecting the schema itself rather than needing to audit stored data instance
  by instance.

## Assumptions

- Storage is populated by a separate process (the backfill/sync spec, not this one) — this spec
  defines the shape data lands in, not how it gets there.
- A trail identifier stable enough to key storage on already exists (the same `trailId` used
  throughout the existing API responses) — no new identity scheme is introduced here.
- Recording a last-written timestamp per entity (FR-010, FR-011) is standard practice for any
  store that will eventually need re-sync/staleness handling, and costs nothing to include now
  even though the re-sync logic itself is a later spec. Per-entity rather than per-trail
  granularity follows directly from the independent-refresh decision above.
- Conditions predictions and weather forecast data are permanently out of scope for this
  storage layer, not just deferred — per the project constitution's endpoint-separation
  principle, they're computed live and never persisted here.
- "Retrievable independently" (FR-004, User Story 4) means the map view's cost doesn't grow with
  how much detail data each trail has — it does not imply anything about how the data is
  physically organized, which is a planning-stage decision.
