# Contract: Trail-List Dependency (assumed, not built by this feature)

**Status: resolved.** `GET /trails` now exists (`server/app/routers/trails.py`'s `list_router`,
backed by `server/app/services/trail_list.py`), returning a bare `TrailMarker[]` (not the
`{"trails": [...]}` wrapper guessed below - a placeholder guess, not a commitment, per this doc's
own framing). `client/src/api/trails.ts`'s `listTrails()` calls it directly; the fixture file this
doc describes has been removed. Left below as the historical record of the assumption this feature
made.

Per spec.md's Assumptions, this feature depends on a backend capability to enumerate all
backfill-eligible trails for map markers. That endpoint does not exist yet (today's backend only
supports per-trail-id lookups: `/trails/{id}/info`, `/activity`, `/geometry`) and building it is
explicitly out of scope for this feature. This document exists so:

1. The frontend's `listTrails()` function (`client/src/api/trails.ts`) has a concrete shape to
   code against now, via a local mock/fixture, instead of guessing mid-implementation.
2. Whoever eventually builds this endpoint has a clear target shape, derived from what the map
   markers actually need (data-model.md's `TrailMarker`) - nothing more.

## Assumed request

```
GET /trails
```

(Path/method is a placeholder guess consistent with the existing `/trails/{id}/...` convention in
`server/app/routers/trails.py` - not a commitment this feature makes on the backend's behalf.)

## Assumed response shape

```json
{
  "trails": [
    { "trailId": "10024848", "name": "Cup and Saucer Trail", "latitude": 45.85331, "longitude": -82.11391 }
  ]
}
```

Deliberately minimal - just what a marker needs (data-model.md's `TrailMarker`), not a full
`/info`-style payload per trail. Traces to `trails.name`/`latitude`/`longitude` in the existing
Postgres schema (`specs/002-trail-data-storage-schema`), which already has `idx_trails_location`
sitting ready for exactly this kind of query.

## What the frontend does until this exists

`listTrails()` is implemented against this exact shape from the start, but pointed at a small
local JSON fixture (e.g. `client/src/api/trailListFixture.json`, populated from a one-off export
of the real `trails` table - not hand-written fake data) behind a single swap point, so switching
to the real endpoint later is a one-line change (the fetch URL), not a rewrite. This fixture
approach is called out explicitly in tasks.md rather than left implicit, so it's visible as
temporary scaffolding, not mistaken for a permanent design choice.
