# Implementation Plan: Trail Data Storage Schema

**Branch**: `002-trail-data-storage-schema` | **Date**: 2026-08-18 | **Spec**: [spec.md](./spec.md)

**Input**: Feature specification from `/specs/002-trail-data-storage-schema/spec.md`

## Summary

Define a Postgres schema for the trail data the frontend actually displays: three independently
refreshable entities (trail overview, popularity aggregate, route geometry), each with its own
`updated_at` freshness timestamp (per the clarification resolving FR-011). Fixed-shape fields
become real typed columns; only genuinely irregular fields (surface composition, feature tags,
month/day-of-week count maps, route coordinates) use JSONB, per constitution Principle X. This
feature delivers the schema as plain SQL DDL plus documentation — no Python/ORM code, no
backfill process, no service-layer changes. Those are separate, later specs.

## Technical Context

**Language/Version**: SQL (PostgreSQL DDL) — no application-language dependency introduced by
this feature. Deliberately deferring driver/ORM choice (psycopg2 vs. SQLAlchemy vs. something
else) to the service-migration spec that will actually write queries against this schema —
committing to that now would be a HOW decision this spec doesn't need to make.

**Primary Dependencies**: PostgreSQL 15+ (any version with solid native JSONB support; nothing
here needs a version-specific feature beyond that)

**Storage**: PostgreSQL — three tables (`trails`, `trail_activity`, `trail_geometry`), described
in data-model.md

**Testing**: `psql`-driven validation (DDL applies cleanly; representative INSERT/SELECT per
table round-trips correctly) — no pytest, since this feature introduces no Python code

**Target Platform**: Wherever the app's Postgres instance runs (local dev now; hosting choice is
out of scope for this feature)

**Project Type**: Schema/infrastructure addition — no new top-level project; SQL lives under a
new `server/db/` directory since this storage exists to back `server/`'s eventual queries, even
though nothing in `server/app/` is touched yet

**Performance Goals**: Not specified by the spec beyond SC-002 ("map marker data retrievable
without loading full detail data") — satisfied structurally by `trails` holding identity/location
directly queryable without joining `trail_activity`/`trail_geometry`, not by a numeric target

**Constraints**:
- Constitution Principle VII (Pipeline-Gated Trail Data): schema itself can't enforce "only
  fully-enriched trails get stored" — that's a population-time rule for the future backfill spec
  to uphold. This spec's job is to make sure nothing in the schema *works against* that rule
  (e.g., no default values that would let a trail exist with fabricated data).
- Constitution Principle IX (Selective Field Storage): every column maps to exactly one field
  enumerated in spec.md's FR-001–FR-004 — no extra columns "just in case."
- Constitution Principle X (Scoped JSONB Usage): JSONB only for `surface_types`, `features`,
  `by_month`, `by_day_of_week`, `geometry` — everything else typed.
- Spec FR-011 (independent refresh): `trail_activity` and `trail_geometry` must not require
  touching `trails` to update, and vice versa — three tables, not one wide table, follows
  directly from this.

**Scale/Scope**: Same personal/small-scale traffic assumption as the rest of this app (per the
weather feature's plan.md) — no partitioning, sharding, or read-replica concerns here.

## Constitution Check

*GATE: Must pass before Phase 0 research. Re-check after Phase 1 design.*

| Principle | Check | Result |
|---|---|---|
| I. Endpoint Separation | Not applicable — no endpoints in this feature | N/A |
| II. Feature Parity (Training/Inference) | Not applicable — no model features involved | N/A |
| III. Forecast Horizon Hard Boundary | Not applicable — no weather/forecast data in this schema | N/A |
| IV–VI. UI-shape principles | Not applicable — no UI in this feature | N/A |
| VII. Pipeline-Gated Trail Data | Schema has no default-populated rows and no seed data — a `trails` row only ever exists because something explicitly inserted it (the future backfill process), which is where the pipeline-completion gate is actually enforced | PASS |
| VIII. Honest Uncertainty in Predictions | Not applicable — no predictions stored here | N/A |
| IX. Selective Field Storage | Every column in data-model.md traces to a spec.md FR-001–FR-004 field; no wholesale-JSON columns | PASS |
| X. Scoped JSONB Usage | JSONB used only for the 5 genuinely irregular fields; all fixed-shape fields (name, difficulty, length, duration, scrambling flag, lat/lng, terrain fields, total review count) are typed columns | PASS |

No violations. Complexity Tracking table is not needed.

**Post-design re-check**: `contracts/schema.sql` confirmed against the table above — `trails`
has no default-populated data and no seed rows (Principle VII still holds structurally); every
column in all three tables traces to a spec.md FR-001–FR-004 field per data-model.md's table
(Principle IX holds); JSONB used only on `surface_types`, `features`, `by_month`,
`by_day_of_week`, `geometry` — the exact five, nothing more (Principle X holds). No drift
between the plan and the actual DDL.

## Project Structure

### Documentation (this feature)

```text
specs/002-trail-data-storage-schema/
├── plan.md              # This file
├── research.md          # Phase 0 output
├── data-model.md         # Phase 1 output
├── quickstart.md         # Phase 1 output
├── contracts/            # Phase 1 output
│   └── schema.sql        # The actual DDL - this feature's real deliverable
└── tasks.md              # Phase 2 output (/speckit-tasks — not created here)
```

### Source Code (repository root)

```text
server/
└── db/
    └── migrations/
        └── 0001_trail_data_storage.sql   # Copy of contracts/schema.sql, versioned for real application

data/    # unchanged - this feature reads nothing from and writes nothing to data/
client/  # unchanged - no frontend code in this feature
```

**Structure Decision**: New `server/db/migrations/` directory — the first database-related path
in this repo. Kept under `server/` (not a new top-level directory) since this storage exists
specifically to back the backend's future queries, matching the existing `server/app/config.py`
comment that `server/` "reads whatever the data pipeline has already produced" — this schema is
the next thing `server/` will read from, just via Postgres instead of flat files. Migration
numbering (`0001_...`) starts a plain sequential convention; no migration *tool* (Alembic, etc.)
is introduced by this feature, since choosing one is a service-layer concern for the next spec.

## Complexity Tracking

*No constitution violations — table not needed.*
