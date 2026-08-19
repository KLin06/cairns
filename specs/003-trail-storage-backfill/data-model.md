# Phase 1 Data Model: Trail Storage Backfill

This feature writes into the schema `specs/002-trail-data-storage-schema` already defines — see
that feature's `data-model.md` and `contracts/schema.sql` for column types/constraints. This
document covers what's new here: the *source → column* mapping for each entity, and which
entities are written under which conditions.

## Eligibility (governs all three entities)

A trail is eligible at all only if `data/datasets/enriched_descriptions/{trail_id}.json` exists.
No file → no rows written for that trail in any of the three tables (FR-001, spec Assumptions).

## `trails`

Source: `enriched_descriptions/{trail_id}.json` (top-level fields, `terrainData.*`), plus
`cleaned_reviews/{trail_id}.json` for one derived field.

| Column | Source | Derivation |
|---|---|---|
| `trail_id` | filename stem of the enriched-description file | direct |
| `name` | `name` | direct (same field `trail_info.py` reads) |
| `latitude` | `latitude` | direct — not exposed by `trail_info.py`'s `TrailInfo` response today; read straight off the source JSON |
| `longitude` | `longitude` | direct, same note as `latitude` |
| `difficulty_rating` | `difficultyRating` | direct, matches `trail_info.py` |
| `length_meters` | `length` | direct, matches `trail_info.py` |
| `duration_minutes` | `durationMinutes` | direct, matches `trail_info.py` |
| `has_scrambling` | `cleaned_reviews/{trail_id}.json` | `_compute_has_scrambling()` logic: fraction of reviews with an `obstacles`/`trailConditions` tag equal to `"scramble"` (case-insensitive) ≥ `SCRAMBLE_THRESHOLD` (0.02); **`False` if the reviews file doesn't exist**, matching `trail_info.py`'s existing behavior |
| `rock_slip_risk` | `terrainData.rock.rockSlipRisk` | direct, matches `trail_info.py`; `NULL` if absent |
| `soil_drainage` | `terrainData.soil.drainage` | direct, matches `trail_info.py`; `NULL` if absent |
| `surface_types` | `surfaceTypes` | direct passthrough as `[{"label", "percentOfSurface"}, ...]`, matches `trail_info.py`'s `SurfaceType` mapping; `NULL` if absent/empty |
| `features` | `features` | direct passthrough as a string array, matches `trail_info.py`; `NULL` if absent |
| `updated_at` | — | `now()` on every insert/update (upsert) |

Always written for every eligible trail (never conditionally skipped) — `latitude`/`longitude`/
`name` are guaranteed present on every `enriched_descriptions` file observed to date, matching
spec 002's `NOT NULL` constraint on those columns.

## `trail_activity`

Source: `cleaned_reviews/{trail_id}.json`.

| Column | Source | Derivation |
|---|---|---|
| `trail_id` | — | same as the `trails` row it references |
| `by_month` | `[].date` | count of reviews per calendar month, keyed `"1"`–`"12"`, matches `activity.py`'s `dates.dt.month.value_counts()` |
| `by_day_of_week` | `[].date` | count of reviews per weekday, keyed `"Mon"`–`"Sun"`, matches `activity.py`'s `dates.dt.dayofweek.value_counts()` |
| `total_reviews` | — | `len(reviews)`, matches `activity.py` |
| `updated_at` | — | `now()` on every insert/update |

**Written only if `cleaned_reviews/{trail_id}.json` exists** (FR-011). If the trail's reviews
list is present but empty, the row is still written with `by_month = {}`, `by_day_of_week = {}`,
`total_reviews = 0` (matches `activity.py`'s existing empty-list handling) — this is the "no
reviews yet" case, distinct from "file doesn't exist," which instead means no row at all.

## `trail_geometry`

Source: `route_geometry/{trail_id}.json`.

| Column | Source | Derivation |
|---|---|---|
| `trail_id` | — | same as the `trails` row it references |
| `geometry` | `.segments` | `FeatureCollection`-shaped GeoJSON: each segment becomes a `LineString` feature, coordinates converted from stored `[lat, lng]` pairs to GeoJSON's `[lng, lat]` order — matches `trail_geometry.py` exactly |
| `updated_at` | — | `now()` on every insert/update |

**Written only if `route_geometry/{trail_id}.json` exists** (FR-004). No row at all otherwise —
this table is legitimately optional per trail regardless of the trail's other eligibility.

## Backfill run outcome (in-memory only, not persisted)

Not a database entity — the per-run report FR-009 requires. Held in memory during a run and
printed/logged at the end; see `contracts/cli.md` for its shape.

| Field | Meaning |
|---|---|
| `trail_id` | which trail this outcome is for |
| `entities_written` | subset of `{trails, trail_activity, trail_geometry}` actually written this run |
| `error` | `None` on success; the exception message if this trail's processing failed partway |
