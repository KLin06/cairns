---
description: "Task list for the Trail Data Storage Schema feature"
---

# Tasks: Trail Data Storage Schema

**Input**: Design documents from `/specs/002-trail-data-storage-schema/`

**Prerequisites**: [plan.md](./plan.md), [spec.md](./spec.md), [research.md](./research.md), [data-model.md](./data-model.md), [contracts/schema.sql](./contracts/schema.sql), [quickstart.md](./quickstart.md)

**Tests**: No automated test suite — plan.md's Technical Context explicitly commits to `psql`-driven validation only, since this feature introduces no Python/application code. Every "test" task below runs a quickstart.md scenario directly against a real Postgres instance.

**Organization**: Tasks are grouped by user story (from spec.md, priority order). Unlike a typical application feature, the schema itself is one indivisible deliverable (one DDL file, three tables that reference each other) — so Foundational covers *applying* the schema, and each story's tasks are the specific validation scenarios that prove that story's requirements hold against the already-applied schema.

## Format: `[ID] [P?] [Story] Description`

- **[P]**: Can run in parallel (different files/queries, no dependencies)
- **[Story]**: Which user story this task belongs to (US1–US4, per spec.md)

## Path Conventions

New `server/db/migrations/` directory (per plan.md's Structure Decision) — no other paths touched.

---

## Phase 1: Setup

**Purpose**: Confirm the target environment is ready

- [x] T001 Confirm a local/dev PostgreSQL 15+ instance is reachable via `$DATABASE_URL` (quickstart.md Prerequisites) — no code, environment check only

---

## Phase 2: Foundational (Blocking Prerequisites)

**Purpose**: Get the schema itself into a real database — every story below validates against this

**⚠️ CRITICAL**: No user story task can begin until this phase is complete

- [x] T002 Copy [contracts/schema.sql](./contracts/schema.sql) to `server/db/migrations/0001_trail_data_storage.sql` as the versioned migration file (plan.md's Structure Decision) — no content changes, this is the DDL becoming a real repo artifact
- [x] T003 Apply the migration: `psql "$DATABASE_URL" -f server/db/migrations/0001_trail_data_storage.sql` (quickstart.md "Apply the schema") — confirm all three tables (`trails`, `trail_activity`, `trail_geometry`), their `CHECK` constraints, the foreign keys, and `idx_trails_location` are created with zero errors

**Checkpoint**: Schema exists in a real database. Every task below is validation against it, not construction.

---

## Phase 3: User Story 1 - Trail overview info available from storage (Priority: P1) 🎯 MVP

**Goal**: A trail's full overview record (name, difficulty, length, duration, scrambling flag, surface composition, terrain, features) round-trips through storage exactly as written.

**Independent Test**: quickstart.md Scenario 1 — insert a representative trail, read it back, confirm every field including the JSONB arrays matches exactly.

- [x] T004 [P] [US1] Run quickstart.md Scenario 1 — full trail overview insert/select round-trip, including `surface_types`/`features` JSONB arrays (spec FR-001, User Story 1 Scenario 1)
- [x] T005 [P] [US1] Run quickstart.md Scenario 2 — trail with unknown terrain fields (`rock_slip_risk`/`soil_drainage` both `NULL`), confirm `NULL` is distinguishable from a placeholder value (spec FR-009, Edge Cases)
- [x] T006 [P] [US1] Run quickstart.md Scenario 7 — attempt an insert with a malformed `features` shape (a JSON string instead of an array), confirm the `features_is_array` check constraint rejects it (research.md #4, constitution Principle X)

**Checkpoint**: Trail overview data is fully validated — the MVP slice of this schema is proven.

---

## Phase 4: User Story 4 - Trail identity and location available for map display (Priority: P1)

**Goal**: Trail identity + coordinates can be retrieved without paying the cost of loading a trail's full overview/activity/geometry data.

**Independent Test**: quickstart.md Scenario 8 — an `EXPLAIN`'d identity/location query touches only `trails`, no join to the other two tables.

- [x] T007 [US4] Run quickstart.md Scenario 8 — confirm a `trail_id, name, latitude, longitude` query plan touches only `trails` (spec FR-004, SC-002)
- [x] T008 [US4] As part of Scenario 8, confirm a location-filtered query (`WHERE latitude BETWEEN ... AND longitude BETWEEN ...`) uses `idx_trails_location` in its plan (spec SC-002)

**Checkpoint**: Map-display data access is proven independent of detail-data cost — both P1 stories (US1, US4) now hold.

---

## Phase 5: User Story 2 - Trail popularity aggregates available from storage (Priority: P2)

**Goal**: A trail's popularity aggregate (by-month, by-day-of-week, total reviews) round-trips through storage, including the zero-reviews case, and can't exist for a trail that has no overview record.

**Independent Test**: quickstart.md Scenario 3 — insert both a populated and a zero-reviews aggregate, confirm both round-trip correctly (the zero case as empty objects/`0`, not an absent row).

- [x] T009 [P] [US2] Run quickstart.md Scenario 3 — populated aggregate and zero-reviews aggregate, confirm both round-trip exactly (spec FR-002, User Story 2 Scenarios 1–2)
- [x] T010 [P] [US2] Run quickstart.md Scenario 6 — attempt inserting `trail_activity` for a `trail_id` with no `trails` row, confirm the foreign key rejects it (research.md #2, spec Edge Cases)

**Checkpoint**: Popularity aggregate storage is proven, including its dependency on an overview record already existing.

---

## Phase 6: User Story 3 - Trail route geometry available from storage (Priority: P2)

**Goal**: A trail's route geometry round-trips through storage when present, and its absence for a trail is a "no row," not an error.

**Independent Test**: quickstart.md Scenario 4 — insert geometry for one trail, confirm a trail with none on record has zero rows in `trail_geometry`, no error.

- [x] T011 [P] [US3] Run quickstart.md Scenario 4 — geometry insert/select round-trip and the "no geometry on record" zero-row case (spec FR-003, User Story 3 Scenarios 1–2)
- [x] T012 [P] [US3] Run quickstart.md Scenario 9 — attempt an insert with a malformed `geometry` shape, confirm the `geometry_is_object` check constraint rejects it (research.md #4, constitution Principle X)

**Checkpoint**: All four user stories are independently validated against the applied schema.

---

## Phase 7: Polish & Cross-Cutting Concerns

**Purpose**: Validation that spans all three tables together, not any single story

- [x] T013 Run quickstart.md Scenario 5 — update `trail_activity` for a trail, confirm `trails.updated_at` is unchanged, proving the three tables are independently refreshable end-to-end (spec FR-011, the resolved clarification)
- [x] T014 [P] Re-check the Constitution Check table in `plan.md` (Principles VII, IX, X) against the applied schema — confirm no drift between `contracts/schema.sql` and what plan.md claims
- [x] T015 [P] Run the full quickstart.md Cleanup step (`DROP TABLE ... CASCADE`) to confirm the schema tears down cleanly, then re-apply T003 to leave the dev database in the expected state for the next feature (the ETL/backfill spec)

---

## Dependencies & Execution Order

### Phase Dependencies

- **Setup (Phase 1)**: No dependencies — start immediately
- **Foundational (Phase 2)**: Depends on Setup — BLOCKS all user stories (the schema must exist before any story can be validated against it)
- **User Story 1 (Phase 3)**: Depends on Foundational only
- **User Story 4 (Phase 4)**: Depends on Foundational only — independent of US1 (queries only `trails`, same table US1 populates, but a different query shape — no data dependency on US1's specific test rows since T007/T008 insert their own)
- **User Story 2 (Phase 5)**: Depends on Foundational; T010 specifically also depends on `trails` having at least the schema (not specific data) in place to prove the FK constraint
- **User Story 3 (Phase 6)**: Depends on Foundational only
- **Polish (Phase 7)**: Depends on all four user stories being validated

### Parallel Opportunities

- T004, T005, T006 (all US1) touch different scenarios against the same tables and can run in parallel
- Once Foundational is done, US1, US4, US2, and US3 phases have no dependencies on each other and could be validated in any order or in parallel — priority order (P1s first: US1, US4) is still recommended so the MVP slice is confirmed first
- T014 and T015 (Polish) are independent of each other

---

## Implementation Strategy

### MVP First (User Story 1 Only)

1. Phase 1 (Setup) → Phase 2 (Foundational) → Phase 3 (US1)
2. **STOP and VALIDATE**: T004–T006 all pass — trail overview data is proven to round-trip correctly
3. This alone confirms the schema's core entity (the one every other table's FK depends on) is sound

### Incremental Delivery

1. Setup + Foundational → schema applied to a real database
2. US1 → overview data proven (MVP)
3. US4 → map-display access pattern proven independent of detail-data cost
4. US2 → popularity aggregates proven, including the FK dependency on US1's table
5. US3 → route geometry proven, including its own shape guardrail
6. Polish → cross-table independence (the whole point of the FR-011 clarification) proven end-to-end, constitution re-check, clean teardown/reapply

## Notes

- No `[Story]` label on Setup/Foundational/Polish tasks, per the checklist format rules.
- Every task is a `psql` session against `contracts/schema.sql` (via the copied migration file) — nothing here writes Python, matching plan.md's explicit deferral of driver/ORM choice to the next spec.
- Since this feature has no separable "build" work per story (the DDL is one file, applied once), story phases here validate rather than construct — that's a legitimate shape for an infrastructure/schema feature, not a shortcut.
