# Phase 1 Data Model: Trail Data Storage Schema

Three tables, each independently refreshable (spec FR-011), each with its own `updated_at`.
Full DDL is the actual contract — see [contracts/schema.sql](./contracts/schema.sql). This file
explains the shape and traces every column back to a spec requirement.

## `trails` (overview record)

| Column | Type | Nullable | Traces to |
|---|---|---|---|
| `trail_id` | `TEXT` (PK) | no | identity — FR-004 |
| `name` | `TEXT` | no | FR-001, FR-004 |
| `latitude` | `DOUBLE PRECISION` | no | FR-004 |
| `longitude` | `DOUBLE PRECISION` | no | FR-004 |
| `difficulty_rating` | `INTEGER` | yes | FR-001 |
| `length_meters` | `DOUBLE PRECISION` | yes | FR-001 |
| `duration_minutes` | `INTEGER` | yes | FR-001 |
| `has_scrambling` | `BOOLEAN` | no | FR-001 (derived boolean, per feature description — not raw review data) |
| `rock_slip_risk` | `TEXT` | yes | FR-001 (nullable — Edge Cases: unknown terrain coverage) |
| `soil_drainage` | `TEXT` | yes | FR-001 (nullable — same reason) |
| `surface_types` | `JSONB` | yes | FR-001, FR-008 — array of `{label, percentOfSurface}` |
| `features` | `JSONB` | yes | FR-001, FR-008 — array of strings |
| `updated_at` | `TIMESTAMPTZ` | no | FR-010, FR-011 |

Why `latitude`/`longitude`/`name` are `NOT NULL` while most other fields are nullable: FR-004
requires identity+location to always be independently retrievable and meaningful (map markers
depend on it existing), whereas difficulty/length/duration/terrain are exactly the fields
spec.md's Edge Cases says can be legitimately unknown for a given trail.

`surface_types` shape: `[{"label": "natural", "percentOfSurface": 99.33}, ...]` — mirrors
`server/app/schemas.py`'s `SurfaceType`.

## `trail_activity` (popularity aggregate)

| Column | Type | Nullable | Traces to |
|---|---|---|---|
| `trail_id` | `TEXT` (PK, FK → `trails.trail_id`) | no | FR-002 |
| `by_month` | `JSONB` | no | FR-002, FR-008 — object, e.g. `{"1": 12, "8": 210}` |
| `by_day_of_week` | `JSONB` | no | FR-002, FR-008 — object, e.g. `{"Mon": 40, "Sat": 190}` |
| `total_reviews` | `INTEGER` | no | FR-002 |
| `updated_at` | `TIMESTAMPTZ` | no | FR-010, FR-011 |

Empty-but-present is the "no reviews" case (spec User Story 2, Scenario 2): `by_month = '{}'`,
`by_day_of_week = '{}'`, `total_reviews = 0` — a row still exists, just with zeroed contents,
matching `server/app/schemas.py`'s `ActivityResponse` shape exactly.

## `trail_geometry` (route geometry)

| Column | Type | Nullable | Traces to |
|---|---|---|---|
| `trail_id` | `TEXT` (PK, FK → `trails.trail_id`) | no | FR-003 |
| `geometry` | `JSONB` | no | FR-003, FR-008 — GeoJSON `FeatureCollection` |
| `updated_at` | `TIMESTAMPTZ` | no | FR-010, FR-011 |

No row at all is the "no geometry on record" case (spec User Story 3, Scenario 2) — this table
is optional per trail, unlike `trail_activity` which always has a row (even if zeroed) once a
trail exists at all.

`geometry` shape: the same GeoJSON `FeatureCollection` of `LineString` features `server/app/schemas.py`'s `RouteGeometry` already defines.

## Relationships

```
trails (1) ──< trail_activity (0..1)
       (1) ──< trail_geometry (0..1)
```

Both child tables reference `trails.trail_id`, `ON DELETE CASCADE` (research.md #2). Neither
relationship is required to exist (`trail_activity`/`trail_geometry` rows are populated
independently and may lag or be absent — FR-011, User Story 3 Scenario 2), but neither can
exist without a `trails` row already present (Edge Cases: overview always precedes the others,
enforced here by the foreign key rather than left as an assumption).
