# Phase 0 Research: Trail Data Storage Schema

## 1. Three tables vs. one wide table

**Decision**: Three tables — `trails`, `trail_activity`, `trail_geometry` — each keyed on
`trail_id`, `trail_activity` and `trail_geometry` holding a foreign key to `trails.trail_id`.

**Rationale**: Directly required by FR-011 (independent refresh, resolved via the clarification
session): if all three lived in one row, updating just the popularity aggregate would mean
rewriting (or `UPDATE`-ing specific columns of) a row that also holds overview and geometry data,
and there'd be no clean way to give each a distinct `updated_at`. Three tables, each with its own
`updated_at`, makes "refresh activity without touching geometry" a plain `UPDATE ... WHERE
trail_id = ...` against one table, no coordination needed.

**Alternatives considered**:
- *One `trails` table with all fields, one `updated_at`* — rejected: violates FR-011 directly,
  was the exact case the clarification question ruled out (Option A).
- *One `trails` table with per-column timestamps (`overview_updated_at`,
  `activity_updated_at`, `geometry_updated_at`)* — technically achieves independent freshness
  tracking without extra tables, but conflates the "does this trail exist in storage" identity
  with three logically distinct kinds of data (attributes vs. behavioral rollup vs. shape data,
  as spec.md's Key Entities section already frames them) — coupling their nullability/constraints
  awkwardly. Three tables keep each entity's own constraints clean (e.g. `trail_geometry` is
  allowed to have no row for a trail at all, vs. a nullable JSONB column with an unclear "not yet
  fetched" vs. "genuinely has none" distinction).

## 2. Foreign key relationship between the three tables

**Decision**: `trail_activity.trail_id` and `trail_geometry.trail_id` are foreign keys
referencing `trails.trail_id`, `ON DELETE CASCADE`.

**Rationale**: Spec.md's Edge Cases section already establishes that a trail only ever has
activity/geometry data because it first has an overview record (Principle VII gates entry into
storage at all) — a foreign key makes that invariant enforced by the database, not just assumed
by whatever code populates it later. `ON DELETE CASCADE` matches "these are logically owned by
the trail" — if a trail's overview record is ever removed (e.g., it fails re-validation in a
future pipeline run), its activity/geometry shouldn't become orphaned rows with no owner.

**Alternatives considered**:
- *No foreign key, just a shared `trail_id` convention* — rejected: makes the "overview always
  exists first" invariant something every future writer has to remember and get right themselves,
  instead of the database refusing an invalid insert.
- *`ON DELETE RESTRICT`* — considered, but would mean an overview record could never be removed
  while activity/geometry still reference it, which seems like the wrong default for data that's
  meant to be refreshable/replaceable; `CASCADE` fits the "owned by" relationship better.

## 3. Primary key type for `trail_id`

**Decision**: `trail_id` is `TEXT`, not an integer.

**Rationale**: Every existing API response (`server/app/schemas.py`'s `TrailInfo.trailId`,
`ActivityResponse.trailId`, etc.) already treats `trailId` as a string, and it's sourced from
AllTrails' own trail IDs, which this app has no control over the format of. Introducing a
separate integer surrogate key would add a layer of indirection with no benefit — nothing in
spec.md calls for one, and it would mean every query needs a join or lookup just to go from the
ID the API already uses to the row that matches it.

**Alternatives considered**:
- *Integer surrogate primary key + a unique `trail_id` column* — rejected as unneeded complexity;
  no spec requirement points to needing it, and it would only add an indirection cost.

## 4. JSONB shape validation

**Decision**: Add `CHECK` constraints on each JSONB column asserting its top-level JSON type
(e.g. `jsonb_typeof(surface_types) = 'array'`), rather than leaving JSONB columns fully
unconstrained.

**Rationale**: Constitution Principle X scopes JSONB to "genuinely irregular" fields, but
"irregular" describes item-level shape (a list can have any number of items, an item's own
fields can vary), not "anything goes at the top level." A `surface_types` value that's
accidentally a string or object instead of an array is a bug, and a `CHECK` constraint catches
it at write time instead of silently corrupting data that a future reader assumes is
list-shaped. This is a cheap, standard Postgres guardrail — not full JSON Schema validation,
which would be overkill for this feature's actual need.

**Alternatives considered**:
- *No constraint at all (bare `jsonb`)* — rejected: too permissive given Principle X's intent;
  a malformed value would only surface as a bug in whatever reads it later, in the next spec.
- *Full JSON Schema validation via an extension* — rejected as more machinery than this feature's
  actual risk (top-level type mismatches) justifies.

## 5. Handling "field unknown" (spec FR-009, Edge Cases)

**Decision**: Nullable typed columns for fields that can be genuinely unknown (`terrain fields`
in particular — spec.md's Edge Cases explicitly calls out trails outside soil-survey coverage).
`NULL` means "unknown," never a sentinel value like `-1` or `""`.

**Rationale**: This is standard SQL practice and directly satisfies FR-009's requirement that an
unknown field be distinguishable from a zero/empty value — `NULL` already has exactly that
semantic in SQL, no extra design needed.

**Alternatives considered**: none seriously — this is the obvious mechanism SQL already provides
for exactly this requirement.

---

All `NEEDS CLARIFICATION` items from Technical Context are resolved above (there were none
remaining after the `/speckit-clarify` session — Technical Context's one deliberate deferral,
the driver/ORM choice, is an explicit scope decision, not an unresolved unknown). No open
questions remain before Phase 1 design.
