# Feature Specification: Trail Storage Backfill

**Feature Branch**: `003-trail-storage-backfill`

**Created**: 2026-08-18

**Status**: Draft

**Input**: User description: "Backfill the trails/trail_activity/trail_geometry tables from the
existing pipeline output in data/datasets/, reusing existing field-derivation logic rather than
reimplementing it. Only trails that completed the full scrape/clean/enrich pipeline are
eligible. The three tables are independently refreshable, so populate each independently per
trail rather than as one all-or-nothing write."

## User Scenarios & Testing *(mandatory)*

### User Story 1 - Populate storage from a trail's existing pipeline output (Priority: P1)

For a trail that has completed the full scrape/clean/enrich pipeline, the backfill process
reads that trail's existing output files and writes its overview record, popularity aggregate,
and route geometry (when present) into storage — turning what's currently only readable as flat
files into queryable, storage-backed trail data.

**Why this priority**: This is the entire point of the feature — without it, the storage schema
built in the prior feature has no data in it at all.

**Independent Test**: Run the backfill against a single fully-enriched trail, then confirm all
three entities for that trail exist in storage with values matching what the equivalent existing
API endpoints (`/trails/:id/info`, `/trails/:id/activity`, `/trails/:id/geometry`) already
compute from the same source files.

**Acceptance Scenarios**:

1. **Given** a trail with a complete enriched description, cleaned reviews, and route geometry
   on disk, **When** the backfill runs for that trail, **Then** its overview record, popularity
   aggregate, and route geometry all appear in storage, matching what the existing read-path
   services already derive from the same files.
2. **Given** a trail with a complete enriched description and cleaned reviews but no route
   geometry on disk, **When** the backfill runs for that trail, **Then** its overview record and
   popularity aggregate appear in storage, and no route geometry record is created — this is not
   treated as a failure.

---

### User Story 2 - Skip trails that haven't completed the pipeline (Priority: P1)

The backfill process only writes data for trails that have actually completed the full
scrape/clean/enrich pipeline — a trail with partial or missing pipeline output is left out of
storage entirely, not written with placeholder or partial data.

**Why this priority**: This is what actually satisfies the storage schema's own
pipeline-completion requirement (carried over from the prior feature, which could define the
rule but not enforce it) — without this, storage integrity depends on nothing.

**Independent Test**: Run the backfill against a trail directory containing both fully-enriched
and partially-processed trails, then confirm only the fully-enriched ones end up in storage.

**Acceptance Scenarios**:

1. **Given** a trail with no enriched description on disk at all, **When** the backfill runs,
   **Then** that trail has no overview record, popularity aggregate, or geometry record written
   to storage.
2. **Given** a mix of eligible and ineligible trails, **When** the backfill runs across all of
   them, **Then** only the eligible trails' data appears in storage afterward — ineligible
   trails are silently skipped, not treated as errors that halt the run.

---

### User Story 3 - Re-run the backfill safely (Priority: P2)

The backfill can be run again — after a trail's pipeline output changes (re-enrichment), after
fixing a bug in the backfill itself, or just to pick up newly-eligible trails — without
duplicating data or requiring storage to be wiped first.

**Why this priority**: Pipeline output isn't static (APP_SPEC.md's own open questions flag
re-enrichment as a real future case) — a backfill that can only ever run once against an empty
database would make every future re-sync a manual, risky, destructive operation instead of a
routine one.

**Independent Test**: Run the backfill twice in a row against the same trail with unchanged
source data, then confirm storage ends up in the same state as a single run (no duplicate rows,
no error on the second run).

**Acceptance Scenarios**:

1. **Given** a trail already backfilled once, **When** the backfill runs again for that trail
   with unchanged source data, **Then** storage reflects the same values as before, with no
   duplicate rows and no error.
2. **Given** a trail already backfilled once, **When** its underlying enriched description
   changes and the backfill runs again, **Then** that trail's overview record in storage reflects
   the updated values, and its `updated_at` (per the prior feature's independent-refresh design)
   reflects the new write.
3. **Given** a trail whose popularity aggregate needs refreshing but whose overview record and
   route geometry are unchanged, **When** the backfill runs, **Then** only the popularity
   aggregate's stored values and `updated_at` change — the overview record and route geometry
   are left untouched, consistent with the three entities being independently refreshable.

### Edge Cases

- What happens when a trail's enriched description exists but is missing an expected field
  entirely (e.g., no terrain data because it's outside soil-survey coverage)? That field is
  written to storage as genuinely unknown (matching the storage schema's own handling of unknown
  fields), not skipped or defaulted to a placeholder.
- What happens when one trail's backfill fails partway through (e.g., malformed source data)?
  It does not stop the run for other trails — the failure is isolated to that trail, and the run
  continues, surfacing which trail(s) failed at the end.
- What happens to a trail's storage record if that trail's source files are later deleted
  entirely (e.g., removed from the pipeline's output)? Out of scope for this feature — this
  process only adds/updates data for trails whose source files currently exist; removing
  storage records for trails that no longer have source data is a separate concern.
- What happens when an eligible trail (has an enriched description) has no cleaned-reviews file
  on disk at all? Its overview record is still written — the popularity-derived scrambling signal
  defaults to "no scrambling" for that trail, matching how the existing read-path already treats
  a missing reviews file for that specific field. Its popularity aggregate, however, is not
  written at all (not written as zeroed) — a missing reviews file means "not yet available," which
  is a different state from "available and empty," and only the latter is what a zeroed aggregate
  represents. No fully-enriched trail currently on disk hits this case, but the rule holds for
  when one does.

## Requirements *(mandatory)*

### Functional Requirements

- **FR-001**: The process MUST determine, for each trail, whether it has completed the full
  scrape/clean/enrich pipeline, and MUST only write that trail's data to storage if it has.
- **FR-002**: The process MUST derive each trail's overview record fields using the same
  field-mapping and derivation logic the existing read-path services already use for the
  equivalent API responses — not a separate, newly-written interpretation of the same source
  files.
- **FR-003**: The process MUST derive each trail's popularity aggregate using the same
  aggregation logic the existing read-path service already uses for the equivalent API response.
- **FR-004**: The process MUST write a trail's route geometry to storage when that trail has
  route geometry on disk, and MUST NOT treat a trail with no route geometry on disk as an error.
- **FR-005**: The process MUST be safe to run more than once against the same trail without
  creating duplicate records — a second run with unchanged source data MUST leave storage in the
  same state as after the first run.
- **FR-006**: The process MUST update a trail's overview record, popularity aggregate, and route
  geometry independently of one another — refreshing one MUST NOT require rewriting or
  re-deriving the other two, consistent with storage's independent-refresh design.
- **FR-007**: When a trail's data changes on disk (e.g., re-enrichment) and the process runs
  again, the affected entity's stored values and freshness marker MUST reflect the new data.
- **FR-008**: A failure processing one trail MUST NOT prevent other trails from being processed
  in the same run.
- **FR-009**: The process MUST report, at the end of a run, which trails succeeded and which
  failed, so a failure isn't silently lost.
- **FR-010**: The process MUST NOT write any field to storage beyond what storage's own schema
  already defines as consuming — it derives and writes exactly those fields, nothing extra from
  any source file.
- **FR-011**: When an eligible trail has no cleaned-reviews file on disk, the process MUST still
  write that trail's overview record (with the scrambling signal defaulting the same way the
  existing read-path already defaults it for a missing reviews file), and MUST NOT write a
  popularity aggregate for that trail — a missing reviews file is not treated the same as an
  empty one.

### Key Entities

- **Backfill run**: One execution of the process across some set of trails (all eligible trails,
  or a specified subset) — produces a per-trail success/failure outcome (FR-008, FR-009).
- **Eligible trail**: A trail whose pipeline output on disk indicates it completed the full
  scrape/clean/enrich pipeline (FR-001) — the population-time gate that storage's own schema
  can't enforce by itself.

## Success Criteria *(mandatory)*

### Measurable Outcomes

- **SC-001**: After running the process against the full set of currently fully-enriched trails,
  every one of them has a matching overview record in storage, every one of them that has a
  cleaned-reviews file on disk has a matching popularity aggregate, and every one of them that has
  route geometry on disk has a matching geometry record.
- **SC-002**: Zero trails without a completed pipeline ever appear in storage after a run —
  directly closes the traceability gap the prior feature's storage schema left open (its own
  pipeline-completion requirement had no enforcement point until this feature).
- **SC-003**: Running the process twice in a row with no source data changes produces identical
  storage contents after both runs — no duplication, no drift.
- **SC-004**: A single trail's source-data failure during a run does not reduce the number of
  other trails successfully processed in that same run, compared to a run without that failure.

## Assumptions

- **Idempotent, upsert-based execution** (not one-shot/insert-only) is the intended design — it
  follows directly from storage's independent-refresh design (each entity has its own freshness
  marker specifically to support being refreshed repeatedly) and from re-enrichment being a real,
  expected future event per APP_SPEC.md. This wasn't treated as an open scope question requiring
  clarification, since no other interpretation fits the existing storage design.
- **Eligibility is determined by the presence of a trail's enriched description output on disk**
  (the same file every existing read-path service already treats as the "has this trail been
  through the pipeline" signal — e.g., the 404 checks in the existing `/info` endpoint), not by
  cross-referencing the scrape pipeline's own internal per-stage state tracking. That internal
  state tracking covers a different set of stages (scrape/clean/review-enrich/geometry) than
  description enrichment specifically, and existing services already rely on the enriched
  description file's presence directly rather than that state file — this process follows the
  same convention for consistency.
- This process is populated from whatever pipeline output already exists on disk at the time it
  runs — it does not trigger or wait for any pipeline stage to run, and it does not modify any
  file under `data/datasets/`.
- "Reusing existing derivation logic" (FR-002, FR-003) means the same rules/thresholds/mappings,
  not necessarily calling the exact same functions unmodified — some existing logic may need to
  be factored into a shared location so both the API read-path and this process can use it
  without duplicating it, which is an implementation detail for planning, not a scope question.
- **Only the enriched description is required for trails-table eligibility (FR-001); cleaned
  reviews and route geometry are each independently optional beyond that** (FR-011, edge cases).
  This follows the existing read-path's own asymmetric handling of a missing reviews file: the
  overview record's scrambling signal already defaults safely when reviews are absent, while the
  popularity aggregate has no safe "unknown" default distinct from "empty," so it's withheld
  rather than written as zeroed. In today's data every enriched trail also has both other files,
  so this only matters for future trails that reach the enrich stage before the review/geometry
  stages catch up.
