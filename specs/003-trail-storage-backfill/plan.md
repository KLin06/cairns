# Implementation Plan: Trail Storage Backfill

**Branch**: `003-trail-storage-backfill` | **Date**: 2026-08-18 | **Spec**: [spec.md](./spec.md)

**Input**: Feature specification from `/specs/003-trail-storage-backfill/spec.md`

## Summary

A one-shot-but-repeatable Python script that reads `data/datasets/{enriched_descriptions,
cleaned_reviews, route_geometry}/{trail_id}.json`, derives the three storage entities
(`trails`, `trail_activity`, `trail_geometry`) using the same field-mapping and aggregation
rules the existing FastAPI read-path services already implement, and upserts each entity
independently into the Postgres schema from spec 002. Only trails with an
`enriched_descriptions/{trail_id}.json` file are eligible (FR-001); the other two entities are
each independently optional beyond that (FR-004, FR-011). A per-trail failure is isolated and
reported, never halting the run (FR-008/FR-009).

## Technical Context

**Language/Version**: Python 3.12 (matches `server/`'s existing FastAPI runtime — required, not
just preferred, because FR-002/FR-003 mandate reusing `server/app/services/trail_info.py` and
`activity.py`'s derivation logic directly rather than reimplementing it in another language)

**Primary Dependencies**: `psycopg2-binary` (new — Postgres driver, not yet in any
`requirements.txt`; a raw driver rather than an ORM/query-builder, consistent with this
project's existing minimal-dependency style in both `server/` and `data/scripts/`, and this
script only ever needs a handful of literal upsert statements, not a query layer); `pandas`
(already a `server/` dependency, already used by `activity.py`'s aggregation)

**Storage**: PostgreSQL — the `trails`/`trail_activity`/`trail_geometry` schema from
`specs/002-trail-data-storage-schema/contracts/schema.sql`, applied via
`server/db/migrations/0001_trail_data_storage.sql`. This feature only writes to that existing
schema; it defines no new tables.

**Testing**: `pytest` (already a `server/` dependency) against a disposable local Postgres
database — round-trip tests per FR (derive-and-upsert produces the expected row; missing
optional files leave the corresponding table untouched; a second run is a no-op; a malformed
trail doesn't stop the rest of the batch)

**Target Platform**: Runs wherever `server/`'s Postgres instance is reachable (local dev now,
per `server/.env`'s `DATABASE_URL` — same target as the rest of `server/`)

**Project Type**: Batch/ETL script living inside the existing `server/` project (not a new
top-level project) — it depends on `server/app/services/` directly and shares `server/`'s
`DATABASE_URL`, so it belongs alongside `server/db/migrations/`, not in `data/scripts/` (which
has no Postgres dependency today and whose own README describes it as flat-file-in,
flat-file-out)

**Performance Goals**: Not specified by the spec beyond "a full run completes and reports
results" — today's dataset is ~68 enriched trails, so no batching/streaming/parallelism
requirement exists; a straightforward per-trail loop is sufficient at this scale

**Constraints**:
- Constitution Principle VII (Pipeline-Gated Trail Data): this script *is* the enforcement
  point spec 002 deferred — FR-001/SC-002 require it to skip any trail without an enriched
  description, with no exceptions.
- Constitution Principle IX (Selective Field Storage): the script must write exactly the
  columns in `specs/002-trail-data-storage-schema/data-model.md` — no passthrough of any
  pipeline JSON field not already named there.
- FR-002/FR-003 (reuse, don't reimplement): `_compute_has_scrambling` and the field mapping in
  `trail_info.py`, and the month/day-of-week aggregation in `activity.py`, must be called (after
  minimal refactoring to expose raw derived values instead of only `HTTPException`-raising
  Pydantic-returning endpoints), not re-derived independently.
- FR-005/FR-006 (idempotent, independently-refreshable writes): each of the three entities is
  its own `INSERT ... ON CONFLICT (trail_id) DO UPDATE` — never one combined transaction across
  entities, and never a delete-then-reinsert that would touch `updated_at` on unchanged rows.
- FR-008/FR-009 (isolated failure, end-of-run report): each trail's three upserts are wrapped so
  one trail's exception is caught, recorded, and does not propagate to the next trail.

**Scale/Scope**: ~68 enriched trails today (`data/datasets/enriched_descriptions/` currently has
68 files); same personal/small-scale assumption as the rest of this app — no partitioning or
concurrency needed.

## Constitution Check

*GATE: Must pass before Phase 0 research. Re-check after Phase 1 design.*

| Principle | Check | Result |
|---|---|---|
| I. Endpoint Separation | Not applicable — this feature adds no endpoints | N/A |
| II. Feature Parity (Training/Inference) | Not applicable — no model features involved | N/A |
| III. Forecast Horizon Hard Boundary | Not applicable — no weather/forecast data touched | N/A |
| IV–VI. UI-shape principles | Not applicable — no UI in this feature | N/A |
| VII. Pipeline-Gated Trail Data | This script is the enforcement point: it writes a `trails` row only when `enriched_descriptions/{trail_id}.json` exists (FR-001), and both child tables only ever reference a `trail_id` that already has such a row (schema FK from spec 002) | PASS |
| VIII. Honest Uncertainty in Predictions | Not applicable — no predictions produced or stored here | N/A |
| IX. Selective Field Storage | The script writes exactly the columns spec 002's data-model.md enumerates, derived via the existing services' field mapping — no wholesale JSON dump of any pipeline stage (FR-010) | PASS |
| X. Scoped JSONB Usage | Already satisfied structurally by spec 002's schema; this script doesn't add or reshape any column | N/A (inherited PASS) |

No violations. Complexity Tracking table is not needed.

**Post-design re-check**: Phase 1 artifacts (data-model.md's field-mapping tables, the CLI
contract) confirmed against the table above — no new columns, no new JSONB fields, and the
eligibility gate (Principle VII) is structural (file-existence check before any write), not a
runtime toggle that could be bypassed. No drift from the constraints above.

## Project Structure

### Documentation (this feature)

```text
specs/003-trail-storage-backfill/
├── plan.md              # This file
├── research.md          # Phase 0 output
├── data-model.md        # Phase 1 output — source-field → column mapping per entity
├── quickstart.md        # Phase 1 output
├── contracts/            # Phase 1 output
│   └── cli.md            # The backfill script's CLI contract (invocation, output, exit codes)
└── tasks.md              # Phase 2 output (/speckit-tasks — not created here)
```

### Source Code (repository root)

```text
server/
├── app/
│   └── services/
│       ├── trail_info.py       # existing — refactor to expose raw derived values
│       │                         (name/lat/lng/etc. + has_scrambling) for reuse, not just
│       │                         the HTTPException-raising, Pydantic-returning endpoint path
│       ├── activity.py          # existing — refactor to expose raw aggregation output the
│       │                         same way, for the same reason
│       └── trail_geometry.py    # existing — already returns a plain-enough shape to reuse
│                                   as-is (no HTTPException wrapping needed by the backfill,
│                                   since a missing file is legitimately "skip", not "error")
├── db/
│   ├── migrations/
│   │   └── 0001_trail_data_storage.sql   # existing — schema this feature populates
│   └── backfill.py               # NEW — this feature's actual deliverable: reads
│                                    data/datasets/, derives each entity via the services
│                                    above, upserts into Postgres, prints an end-of-run report
├── tests/
│   └── db/
│       └── test_backfill.py      # NEW — round-trip tests against a disposable local DB
└── requirements.txt               # add psycopg2-binary
```

**Structure Decision**: Everything lives inside the existing `server/` project — no new
top-level project. The backfill script (`server/db/backfill.py`) sits next to the migration it
populates (`server/db/migrations/`) and imports its field-derivation logic from
`server/app/services/`, which is refactored minimally (split "derive the value" from "raise
404/return a Pydantic response") so both the live API and this batch script share one
implementation, per FR-002/FR-003 and the spec's Assumptions section. `data/scripts/` is left
untouched — it has no Postgres dependency today and this feature doesn't give it one; the
backfill only *reads* its output.

## Complexity Tracking

*No Constitution Check violations — this section is not needed.*
