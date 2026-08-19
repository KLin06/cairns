---

description: "Task list for Trail Storage Backfill"
---

# Tasks: Trail Storage Backfill

**Input**: Design documents from `/specs/003-trail-storage-backfill/`

**Prerequisites**: [plan.md](./plan.md), [spec.md](./spec.md), [research.md](./research.md), [data-model.md](./data-model.md), [contracts/cli.md](./contracts/cli.md), [quickstart.md](./quickstart.md)

**Tests**: Included — plan.md's Technical Context commits to `pytest` round-trip tests against a
disposable local Postgres database, so tests are part of this task list, not optional here.

**Organization**: Tasks are grouped by user story (spec.md: US1/US2 are P1, US3 is P2) to enable
independent implementation and testing of each.

## Path Conventions

Single project, living inside the existing `server/` tree (see plan.md's Structure Decision):
- Script: `server/db/backfill.py`
- Refactored services: `server/app/services/trail_info.py`, `activity.py`, `trail_geometry.py`
- Tests: `server/tests/test_backfill.py` (flat, matching the existing convention in
  `server/tests/test_weather.py` — no `tests/db/` subfolder)

---

## Phase 1: Setup

**Purpose**: Get the project ready to hold this feature's code

- [X] T001 Add `psycopg2-binary` to `server/requirements.txt`
- [X] T002 [P] Create `server/db/__init__.py` (empty — makes `db` an importable package alongside `app`, needed for `python -m db.backfill`)
- [X] T003 [P] Add a `test_backfill_db_url` fixture setup note to `server/tests/__init__.py` or a new `server/tests/conftest.py`: reads a `TEST_DATABASE_URL` env var (falling back to `DATABASE_URL`), and skips all backfill tests with a clear message if it's unset — so the suite doesn't hard-fail on machines without a local Postgres

---

## Phase 2: Foundational (Blocking Prerequisites)

**Purpose**: Shared infrastructure every user story's tasks build on — DB connectivity, and the
service-layer refactor that lets the script reuse existing derivation logic instead of
reimplementing it (FR-002/FR-003)

**⚠️ CRITICAL**: No user story phase below can be completed until this phase is done

- [X] T004 Add a `conftest.py` fixture in `server/tests/conftest.py` that connects to `TEST_DATABASE_URL`, applies `server/db/migrations/0001_trail_data_storage.sql` inside a transaction/schema that's rolled back or dropped after each test (or truncates the three tables between tests), and yields a live `psycopg2` connection
- [X] T005 Implement `server/db/connection.py`: `get_connection()` reads `DATABASE_URL` from the environment (via `python-dotenv`/`os.environ`, matching `server/app/config.py`'s existing pattern) and returns a `psycopg2` connection
- [X] T006 [P] Refactor `server/app/services/trail_info.py`: extract a `derive_trail_record(trail_id) -> dict | None` function that returns `None` if `enriched_descriptions/{trail_id}.json` doesn't exist, otherwise a plain dict with `trail_id`, `name`, `latitude`, `longitude`, `difficulty_rating`, `length_meters`, `duration_minutes`, `has_scrambling`, `rock_slip_risk`, `soil_drainage`, `surface_types`, `features` (per data-model.md's mapping table) — built from the same field paths and the existing `_compute_has_scrambling()`. `get_trail_info()` keeps its current signature/behavior (404 + `TrailInfo`) by calling `derive_trail_record()` internally and raising when it returns `None`
- [X] T007 [P] Refactor `server/app/services/activity.py`: extract `derive_trail_activity(trail_id) -> dict | None` that returns `None` if `cleaned_reviews/{trail_id}.json` doesn't exist, otherwise `{"by_month": {...}, "by_day_of_week": {...}, "total_reviews": int}` using the same `pandas` aggregation. `get_trail_activity()` keeps its current signature/behavior (404 + `ActivityResponse`) by calling this internally
- [X] T008 [P] Add `derive_trail_geometry(trail_id) -> dict | None` to `server/app/services/trail_geometry.py`: returns `None` if `route_geometry/{trail_id}.json` doesn't exist, otherwise the same `FeatureCollection`-shaped dict `get_trail_geometry()` already builds (segments → `LineString` features, `[lat,lng]` → `[lng,lat]`). `get_trail_geometry()` keeps its current signature/behavior (404 + `RouteGeometry`) by calling this internally
- [X] T009 Implement `list_eligible_trail_ids() -> list[str]` in `server/db/backfill.py`: lists `*.json` filenames (stem only) under `ENRICHED_DESCRIPTIONS_DIR` (imported from `app.config`)
- [X] T010 Implement upsert helpers in `server/db/backfill.py`: `upsert_trail(conn, record) -> bool`, `upsert_trail_activity(conn, trail_id, agg) -> bool`, `upsert_trail_geometry(conn, trail_id, geometry) -> bool`. Each does `SELECT` the existing row first; if the derived values are identical to what's stored, skip the write entirely (leaves `updated_at` untouched, per FR-005/contracts/cli.md's resolution of the re-run/`updated_at` question); otherwise `INSERT ... ON CONFLICT (trail_id) DO UPDATE SET ..., updated_at = now()`. Returns whether a write happened (used for the run report)

**Checkpoint**: DB connectivity works, all three services expose reusable raw-value derivation, upsert primitives exist. User story implementation can now begin.

---

## Phase 3: User Story 1 - Populate storage from a trail's existing pipeline output (Priority: P1) 🎯 MVP

**Goal**: Running the backfill against a fully-enriched trail writes matching rows to all three
tables, using the existing derivation logic.

**Independent Test**: Run the backfill against one fully-enriched trail; confirm `trails`,
`trail_activity`, `trail_geometry` all contain values matching the equivalent `/info`,
`/activity`, `/geometry` API responses for that trail (quickstart.md steps 2–3).

### Tests for User Story 1

> Write these first; they should fail until the implementation tasks below are done.

- [X] T011 [P] [US1] Test in `server/tests/test_backfill.py::test_process_trail_writes_all_three_entities_for_fully_eligible_trail` — using `tmp_path`-based fake `enriched_descriptions`/`cleaned_reviews`/`route_geometry` fixtures (same pattern as `test_weather.py`'s `enriched_trail` fixture) plus the `conftest.py` DB fixture, assert all three rows exist after processing one trail and match the fixture's derived values
- [X] T012 [P] [US1] Test in `server/tests/test_backfill.py::test_process_trail_skips_geometry_when_absent_but_writes_the_other_two` — no `route_geometry` fixture file; assert `trails`/`trail_activity` rows exist and no `trail_geometry` row exists
- [X] T013 [P] [US1] Test in `server/tests/test_backfill.py::test_process_trail_writes_overview_with_no_scrambling_when_reviews_absent_and_skips_activity` — no `cleaned_reviews` fixture file for an otherwise-eligible trail; assert the `trails` row is written with `has_scrambling = False` (matching `trail_info.py`'s existing default-when-missing behavior) and no `trail_activity` row exists (FR-011 — the reviews-missing analog of T012's geometry-missing case)

### Implementation for User Story 1

- [X] T014 [US1] Implement `process_trail(conn, trail_id) -> dict` in `server/db/backfill.py`: calls `derive_trail_record`, `derive_trail_activity`, `derive_trail_geometry` (T006–T008) and the matching `upsert_*` helpers (T010) for whichever return non-`None`. **Wraps each entity's derive-and-upsert step in its own try/except**: an exception raised while deriving or upserting one entity is caught, does not propagate out of `process_trail`, and is recorded — this is the actual implementation of FR-008 (per-trail failure isolation), not just a shape convention. Returns an outcome dict `{"trail_id", "entities_written": set(...), "error": str | None}`, where `error` holds the caught exception's message if anything failed for this trail (depends on T006–T010)
- [X] T015 [US1] Implement `main()` CLI entry point in `server/db/backfill.py`: `argparse` accepting optional positional `trail_id` args (per contracts/cli.md). **Two branches, both funnel through `process_trail` per trail**: (a) no args → process every id from `list_eligible_trail_ids()` (T009); (b) one or more explicit `trail_id` args → process exactly those ids, bypassing the eligible-trail enumeration (`process_trail`'s own eligibility check in T018 still applies per trail). The loop itself must not stop early if one `process_trail` call reports an error — every trail_id in the batch is always attempted (FR-008 at the batch level, since T014 already guarantees no trail's processing can raise out to this loop)
- [X] T016 [US1] Implement end-of-run reporting in `server/db/backfill.py`: print one line per trail (id, entities written, error if any) and a summary line (attempted/succeeded/failed counts), matching contracts/cli.md's Output section; `if __name__ == "__main__": sys.exit(main())`

**Checkpoint**: `python -m db.backfill <trail_id>` populates all three tables for one trail, matching the read-path. Runnable and independently testable.

---

## Phase 4: User Story 2 - Skip trails that haven't completed the pipeline (Priority: P1)

**Goal**: Trails without a completed pipeline are left out of storage entirely — never written
with partial or placeholder data, never treated as a run-halting error. A single trail's
processing failure (malformed source data, unexpected exception) is likewise isolated and never
halts the batch.

**Independent Test**: Run the backfill against a mix of eligible and ineligible trail directories;
confirm only eligible trails end up in storage, and an explicitly-named ineligible trail produces
a clean "skipped" report line, not an exception (quickstart.md step 4). Separately, run the
backfill against a batch containing one trail with malformed source data; confirm every other
trail in that batch still gets processed (SC-004).

### Tests for User Story 2

- [X] T017 [P] [US2] Test in `server/tests/test_backfill.py::test_process_trail_with_no_enriched_description_writes_nothing` — call `process_trail` for a `trail_id` with no fixture files at all; assert no rows in any of the three tables and the outcome's `entities_written` is empty with no error
- [X] T018 [P] [US2] Test in `server/tests/test_backfill.py::test_main_with_mixed_eligible_and_ineligible_trail_ids_only_writes_eligible` — fixture directory with two trail ids, only one with an enriched description; run `main()` with both ids explicitly passed; assert only the eligible one has rows, and the process exits `0` (per contracts/cli.md: a named-but-ineligible trail is a skip, not a failure)
- [X] T019 [P] [US2] Test in `server/tests/test_backfill.py::test_one_trails_failure_does_not_stop_other_trails_in_the_same_run` — fixture directory with three eligible trail ids; write malformed JSON (or otherwise induce an exception, e.g. via `monkeypatch` raising inside one entity's derivation) for the middle one; run `main()` with no args (full batch) or with all three ids explicit; assert the other two trails still have all their rows written, the broken trail's outcome has a non-`None` `error`, and the process's exit code is non-zero (FR-008/FR-009/SC-004 — the actual isolation behavior, not just the skip case T017/T018 cover)

### Implementation for User Story 2

- [X] T020 [US2] In `server/db/backfill.py`, ensure `process_trail` (T014) treats `derive_trail_record(trail_id) is None` as a clean skip — return `{"trail_id", "entities_written": set(), "error": None, "skipped": True}` without attempting `derive_trail_activity`/`derive_trail_geometry` or any upsert (they're meaningless without a `trails` row to reference, per the FK in spec 002's schema). This is a distinct code path from the try/except failure-handling added in T014 — a missing file is an expected, non-error condition; an unexpected exception during derivation/upsert (T019) is a genuine failure and must be reported as one
- [X] T021 [US2] In `server/db/backfill.py`'s `main()` (T015) and reporting (T016), distinguish skip vs. failure vs. success in the printed report and in the exit-code calculation: exit `0` only if zero trails in the run had `error is not None` (a skip alone never triggers a non-zero exit; any genuine per-trail error does), per contracts/cli.md

**Checkpoint**: Ineligible trails (missing or explicitly-named-but-absent) never produce rows and never fail the run; a genuinely broken trail is isolated, reported, and doesn't block its batch-mates; eligible trails from US1 still work.

---

## Phase 5: User Story 3 - Re-run the backfill safely (Priority: P2)

**Goal**: Running the backfill again — unchanged, or after source data changes, or after a single
entity's source changes — never duplicates rows and only touches the entities that actually
changed.

**Independent Test**: Run the backfill twice with unchanged source data (identical storage, no
duplicate rows, `updated_at` unchanged); then change only one entity's source file and re-run
(only that entity's row and `updated_at` change) (quickstart.md step 5).

### Tests for User Story 3

- [X] T022 [P] [US3] Test in `server/tests/test_backfill.py::test_rerun_with_unchanged_source_is_a_noop` — process the same trail twice with unchanged fixtures; assert row counts and `updated_at` values are identical after both runs
- [X] T023 [P] [US3] Test in `server/tests/test_backfill.py::test_rerun_after_description_change_updates_only_trails_row` — process a trail, capture all three `updated_at` values, edit the fixture's enriched-description file (e.g. change `difficultyRating`), re-process; assert `trails.updated_at` advanced and its changed field matches, while `trail_activity.updated_at`/`trail_geometry.updated_at` are unchanged
- [X] T024 [P] [US3] Test in `server/tests/test_backfill.py::test_rerun_after_reviews_change_updates_only_activity_row` — same pattern, editing the cleaned-reviews fixture instead; assert only `trail_activity.updated_at` advances

### Implementation for User Story 3

- [X] T025 [US3] Verify/adjust the change-detection comparison in `upsert_trail`/`upsert_trail_activity`/`upsert_trail_geometry` (T010) handles every column correctly (in particular `JSONB` columns — compare Python-side dict/list equality against the `SELECT`ed-and-parsed existing value, not raw string equality) so T022–T024 pass

**Checkpoint**: All three user stories pass their independent tests; reruns are safe and minimal.

---

## Phase 6: Polish & Cross-Cutting Concerns

**Purpose**: Documentation and final validation across all stories

- [X] T026 [P] Update `server/README.md`'s Status section with the backfill script's invocation (per contracts/cli.md) and a one-line description of what it populates
- [X] T027 Run through `quickstart.md` end-to-end manually against real `data/datasets/` output and a local Postgres instance, confirming SC-001–SC-004 from spec.md hold for the full ~68-trail dataset

---

## Dependencies & Execution Order

### Phase Dependencies

- **Setup (Phase 1)**: No dependencies
- **Foundational (Phase 2)**: Depends on Setup — BLOCKS all user stories
- **User Story 1 (Phase 3)**: Depends on Foundational only
- **User Story 2 (Phase 4)**: Depends on Foundational; builds directly on US1's `process_trail`/`main` (T014–T016), so implement after US1 even though both are P1
- **User Story 3 (Phase 5)**: Depends on Foundational and on US1's upsert helpers (T010); independent of US2
- **Polish (Phase 6)**: Depends on all desired user stories being complete

### Within Each Phase

- Tests before the implementation tasks they cover (write-first, confirm failing) — note T019 (US2's failure-isolation test) exercises `main()`, so it can only actually run once T015 exists; it's still listed in the Tests subsection for story-grouping consistency, but expect to write it alongside/after T014–T016 in practice
- T014 (process_trail, with failure isolation) before T015 (main) before T016 (reporting) — each builds on the last

### Parallel Opportunities

- T002, T003 (Setup) in parallel
- T006, T007, T008 (the three service refactors) in parallel — different files
- T011, T012, T013 (US1 tests) in parallel
- T017, T018, T019 (US2 tests) in parallel
- T022, T023, T024 (US3 tests) in parallel

---

## Parallel Example: Foundational Phase

```bash
# Launch the three service refactors together (different files, no shared state):
Task: "Refactor trail_info.py to add derive_trail_record()"
Task: "Refactor activity.py to add derive_trail_activity()"
Task: "Add derive_trail_geometry() to trail_geometry.py"
```

---

## Implementation Strategy

### MVP First (User Story 1 Only)

1. Complete Phase 1 (Setup) and Phase 2 (Foundational) — the service refactors and upsert
   primitives are required groundwork, not optional scaffolding, since FR-002/FR-003 forbid
   reimplementing derivation logic
2. Complete Phase 3 (User Story 1) — note this now includes the try/except failure-isolation
   wrapping in T014 (FR-008), not just the happy-path population logic
3. **STOP and VALIDATE**: run quickstart.md steps 1–3 against one real trail
4. This alone proves the schema from spec 002 can hold real data end-to-end

### Incremental Delivery

1. Setup + Foundational → foundation ready
2. Add US1 → validate independently (populates storage for eligible trails, isolates per-entity
   failures within a single trail) — MVP
3. Add US2 → validate independently (ineligible trails cleanly excluded; a broken trail doesn't
   stop its batch-mates, per T019/SC-004) — closes the FR-005/SC-003 traceability gap from
   spec 002's `/speckit-analyze` flag, and the FR-008/SC-004 gap flagged by this feature's own
   `/speckit-analyze` pass
4. Add US3 → validate independently (safe to re-run, minimal writes on unchanged reruns)
5. Polish → docs + full-dataset validation
