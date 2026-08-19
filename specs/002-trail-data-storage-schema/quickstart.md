# Quickstart: Validating the Trail Data Storage Schema

No Python code is involved in this feature — validation is pure SQL against a real Postgres
instance, via `psql`.

## Prerequisites

- A running PostgreSQL 15+ instance and a database to apply the schema to.

## Apply the schema

```bash
psql "$DATABASE_URL" -f specs/002-trail-data-storage-schema/contracts/schema.sql
```

**Expected**: three tables created (`trails`, `trail_activity`, `trail_geometry`), no errors.

## Scenario 1 — trail overview round-trips correctly (User Story 1)

```sql
INSERT INTO trails (trail_id, name, latitude, longitude, difficulty_rating, length_meters,
                     duration_minutes, has_scrambling, rock_slip_risk, soil_drainage,
                     surface_types, features)
VALUES ('10024848', 'Cup and Saucer Trail', 45.85331, -82.11391, 3, 8368.568, 145, true,
        'moderate', 'imperfect',
        '[{"label": "natural", "percentOfSurface": 99.33}, {"label": "gravel", "percentOfSurface": 0.67}]',
        '["Fee required", "Forests", "Lakes"]');

SELECT * FROM trails WHERE trail_id = '10024848';
```

**Expected**: every column comes back exactly as inserted, including the JSONB arrays.

## Scenario 2 — trail with unknown terrain fields (Edge Cases)

```sql
INSERT INTO trails (trail_id, name, latitude, longitude, has_scrambling)
VALUES ('99999999', 'No Terrain Data Trail', 46.0, -83.0, false);

SELECT trail_id, rock_slip_risk, soil_drainage FROM trails WHERE trail_id = '99999999';
```

**Expected**: `rock_slip_risk` and `soil_drainage` come back `NULL` — genuinely unknown, not a
placeholder value (spec FR-009).

## Scenario 3 — popularity aggregate, including the zero-reviews case (User Story 2)

```sql
INSERT INTO trail_activity (trail_id, by_month, by_day_of_week, total_reviews)
VALUES ('10024848', '{"1": 12, "8": 210}', '{"Sat": 190, "Sun": 175}', 975);

INSERT INTO trail_activity (trail_id, by_month, by_day_of_week, total_reviews)
VALUES ('99999999', '{}', '{}', 0);

SELECT * FROM trail_activity WHERE trail_id IN ('10024848', '99999999');
```

**Expected**: both rows present; the second has empty JSON objects and `0`, not absent.

## Scenario 4 — route geometry is optional (User Story 3)

```sql
INSERT INTO trail_geometry (trail_id, geometry)
VALUES ('10024848', '{"type": "FeatureCollection", "features": [{"type": "Feature", "geometry": {"type": "LineString", "coordinates": [[-82.11391, 45.85331], [-82.11289, 45.85402]]}, "properties": {}}]}');

SELECT COUNT(*) FROM trail_geometry WHERE trail_id = '99999999';
```

**Expected**: the geometry insert succeeds; the count for the trail with no geometry on record
is `0` — no row required, no error.

## Scenario 5 — independent refresh (FR-011, the clarification)

```sql
SELECT updated_at FROM trails WHERE trail_id = '10024848';
-- note the timestamp, then:

UPDATE trail_activity SET total_reviews = 976, updated_at = now() WHERE trail_id = '10024848';

SELECT updated_at FROM trails WHERE trail_id = '10024848';
```

**Expected**: `trails.updated_at` is unchanged by the `trail_activity` update — confirms the
two are independently refreshable, not coupled.

## Scenario 6 — referential integrity (research.md #2)

```sql
INSERT INTO trail_activity (trail_id, by_month, by_day_of_week, total_reviews)
VALUES ('00000000', '{}', '{}', 0);
```

**Expected**: fails with a foreign key violation — `trail_activity` cannot reference a
`trail_id` that has no `trails` row.

## Scenario 7 — JSONB shape guardrails (research.md #4)

```sql
INSERT INTO trails (trail_id, name, latitude, longitude, has_scrambling, features)
VALUES ('11111111', 'Bad Features Shape', 45.0, -82.0, false, '"not an array"');
```

**Expected**: fails the `features_is_array` check constraint.

## Scenario 8 — identity/location retrievable independently (User Story 4, SC-002)

```sql
INSERT INTO trails (trail_id, name, latitude, longitude, has_scrambling)
VALUES ('22222222', 'Second Trail', 46.1, -83.1, false);

EXPLAIN SELECT trail_id, name, latitude, longitude FROM trails;
```

**Expected**: the query plan touches only `trails` — no join to `trail_activity` or
`trail_geometry` — confirming map marker data doesn't pay the cost of loading full detail data
(SC-002). A location-scoped variant (`WHERE latitude BETWEEN ... AND longitude BETWEEN ...`)
should show `idx_trails_location` in the plan.

## Scenario 9 — geometry JSONB shape guardrail (research.md #4)

```sql
INSERT INTO trail_geometry (trail_id, geometry)
VALUES ('10024848', '"not an object"');
```

**Expected**: fails the `geometry_is_object` check constraint (note: run before Scenario 4's
insert for this `trail_id`, or against a different trail, since `trail_geometry.trail_id` is a
primary key).

## Cleanup

```sql
DROP TABLE trail_geometry, trail_activity, trails CASCADE;
```
