# Phase 0 Research: Trail Storage Backfill

No `[NEEDS CLARIFICATION]` markers remain in spec.md — the spec's own Assumptions section
already resolved the three open scope questions (idempotency, eligibility signal, optional-file
handling). What's left for this phase is the *technical* decisions the spec deliberately left to
planning.

## 1. Postgres driver

**Decision**: `psycopg2-binary`, called directly (no ORM, no query builder).

**Rationale**: The script needs a handful of literal `INSERT ... ON CONFLICT` statements against
three tables — there's no query surface large enough to justify an ORM's mapping/migration
machinery, and `data/scripts/` and `server/` both already favor minimal, direct dependencies
over frameworks (see `HANDOFF-backfill.md`'s note on this). `psycopg2-binary` avoids requiring a
local `libpq`/build toolchain (unlike plain `psycopg2`), which matters since this runs on
whatever machine has `data/datasets/` checked out, not necessarily a machine already set up to
compile C extensions.

**Alternatives considered**:
- `SQLAlchemy` (Core or ORM) — rejected: no other part of this codebase uses an ORM; would
  introduce a dependency and a mapping layer for three fixed, already-fully-specified tables.
- `psycopg` (v3) — reasonable alternative, but `psycopg2` is what most existing
  Python-plus-Postgres tooling in this ecosystem defaults to and has no async requirement this
  script needs; no material advantage to v3 here.
- `pandas.DataFrame.to_sql` — rejected for the actual upserts: `to_sql` doesn't support
  `ON CONFLICT` upsert semantics natively, and FR-005/FR-006 require upsert-per-entity. `pandas`
  is still used, but only for the `by_month`/`by_day_of_week` aggregation `activity.py` already
  does, exactly as before.

## 2. Where reused derivation logic lives

**Decision**: Refactor `trail_info.py` and `activity.py` minimally to split "derive the value(s)
from the source file" from "turn that into an HTTP response" — e.g. `get_trail_info()` keeps its
existing signature/behavior (404 + Pydantic model) for the API, but the field mapping and
`_compute_has_scrambling()` become directly callable in a form that returns plain values (not an
HTTPException, not a `TrailInfo`) so `server/db/backfill.py` can call them without going through
FastAPI's error-handling path or losing fields `TrailInfo` doesn't carry (`trailId`, `name`,
`latitude`, `longitude` aren't in `TrailInfo` at all today — only `trail_info.py`'s internal
`description` dict has them, straight from `enriched_descriptions/{trail_id}.json`).

**Rationale**: FR-002/FR-003 require reusing the *same rules*, not the same HTTP-shaped
function. `trail_info.py`'s `TrailInfo` response model was designed for what the frontend detail
panel needs (per APP_SPEC.md), which doesn't include lat/lng/trailId as literal fields — those
already exist directly on the source JSON and don't need service-layer derivation at all, just
straight passthrough. `activity.py`'s `get_trail_activity()` already returns everything
`trail_activity` needs in `ActivityResponse`, but it 404s on a missing file where the backfill
needs "skip this entity, don't error" (FR-011) — a plain call-and-catch, or a small internal
split (`_load_reviews_or_none()` / `_aggregate(reviews)`), resolves this without duplicating the
aggregation math itself.

**Alternatives considered**:
- Duplicate the field-mapping/aggregation logic directly in `backfill.py` — rejected: this is
  exactly what FR-002/FR-003 forbid (reimplementing instead of reusing), and it's exactly the
  kind of drift the spec's Assumptions section flagged as needing to be avoided by factoring
  shared logic out, not copying it.
- Have `backfill.py` call the FastAPI route functions (`trail_info()`, `trail_activity()`, etc.)
  directly, catching their `HTTPException`s — rejected: possible, but conflates two different
  eligibility semantics ("404 means this API response can't be served" vs. "missing file means
  skip this one entity for this one trail, keep going") and pulls in FastAPI request/response
  machinery for what's really a plain function call. A direct call to a raw-value-returning
  helper is simpler and matches the "isolated per-trail failure" requirement (FR-008) more
  directly — a `try/except` per entity, not per HTTP call.

## 3. Upsert pattern

**Decision**: One `INSERT ... ON CONFLICT (trail_id) DO UPDATE SET ..., updated_at = now()`
statement per entity per trail — three independent statements, three independent transactions
(or at least three independently-committed statements; no single transaction spans all three
entities for one trail, and no transaction spans multiple trails).

**Rationale**: This is the direct SQL expression of FR-005 (idempotent), FR-006 (independent
refresh), and FR-008 (isolated per-trail failure) together — `trails`, `trail_activity`, and
`trail_geometry` upserts for a given trail don't need to succeed or fail as a unit (spec 002's
independent-refresh design says they never should), and one trail's failure on any of its three
upserts shouldn't roll back or block another trail's.

**Alternatives considered**:
- Delete-then-reinsert per run — rejected: this is not idempotent in the way FR-005 requires
  (SC-003 says "identical storage contents", but delete-then-reinsert would still bump
  `updated_at` on every row every run, which isn't "identical" and contradicts the point of a
  freshness marker) and it would violate FK integrity ordering (`trails` must exist before its
  children — deleting and reinserting it mid-run risks a moment where child rows are orphaned).
- One transaction per trail across all three entities — rejected: ties three independently-
  refreshable entities' success to each other, contradicting spec 002's FR-011 and this spec's
  FR-006 directly (a `trail_geometry` failure shouldn't roll back an otherwise-successful
  `trails`/`trail_activity` write for the same trail).

## 4. Eligible-trail enumeration

**Decision** (already fixed by spec.md's Assumptions, restated here for the plan's traceability):
`os.listdir(ENRICHED_DESCRIPTIONS_DIR)`, filtered to `*.json`, trail_id = filename stem. No
cross-reference to `data/scripts/trails.py`'s `pipeline_state.json`.

**Rationale**: Matches the existing convention every read-path service already uses (file
presence, not the scraper's internal per-stage state file, which tracks a different, broader set
of stages than "has an enriched description").
