# Quickstart: Validate the Trail Storage Backfill

Prerequisites: a reachable Postgres instance with spec 002's schema applied
(`server/db/migrations/0001_trail_data_storage.sql`), `server/.env`'s `DATABASE_URL` pointed at
it, and `data/datasets/` present with at least one fully-enriched trail.

## 1. Apply the schema (if not already applied)

```bash
psql "$DATABASE_URL" -f server/db/migrations/0001_trail_data_storage.sql
```

## 2. Run the backfill against one trail

Pick a trail_id that has all three source files (`enriched_descriptions`, `cleaned_reviews`,
`route_geometry`) — e.g. any file present in all three of
`data/datasets/{enriched_descriptions,cleaned_reviews,route_geometry}/`.

```bash
cd server
python -m db.backfill <trail_id>
```

Expect: exit code `0`, one report line showing all three tables written for that trail.

## 3. Confirm storage matches the existing read-path

```bash
curl localhost:8000/trails/<trail_id>/info
curl localhost:8000/trails/<trail_id>/activity
curl localhost:8000/trails/<trail_id>/geometry
```

```sql
select * from trails where trail_id = '<trail_id>';
select * from trail_activity where trail_id = '<trail_id>';
select * from trail_geometry where trail_id = '<trail_id>';
```

Expect: `difficulty_rating`/`length_meters`/`duration_minutes`/`has_scrambling`/
`rock_slip_risk`/`soil_drainage`/`surface_types`/`features` match the `/info` response 1:1;
`by_month`/`by_day_of_week`/`total_reviews` match `/activity`; `geometry` matches `/geometry`
(User Story 1's Independent Test).

## 4. Confirm ineligible trails are skipped

```bash
python -m db.backfill some-made-up-trail-id-that-does-not-exist
```

Expect: exit code `0` (an explicitly-named ineligible trail is a reported skip, not a failure),
report shows no tables written for it, and:

```sql
select count(*) from trails where trail_id = 'some-made-up-trail-id-that-does-not-exist';
-- 0
```

(User Story 2's Independent Test.)

## 5. Confirm re-running is safe

```bash
python -m db.backfill <trail_id>
python -m db.backfill <trail_id>
```

```sql
select trail_id, updated_at from trails where trail_id = '<trail_id>';
```

Expect: no error on the second run, no duplicate row (PK prevents this structurally), and the
row count in each table is unchanged from after the first run (User Story 3's Independent Test).

## 6. Full-batch run

```bash
python -m db.backfill
```

Expect: exit code `0` if every eligible trail on disk processes cleanly; summary line reports
counts matching the number of files in `data/datasets/enriched_descriptions/` (SC-001); zero
rows in any table for a `trail_id` that has no matching `enriched_descriptions` file (SC-002,
verifiable by comparing `select trail_id from trails` against
`ls data/datasets/enriched_descriptions/`).
