# Contract: `trails` Table Schema Addition

Defines the columns [server/db/migrations/0004_add_model_terrain_features.sql](../../../server/db/migrations/0004_add_model_terrain_features.sql) adds to the existing `trails` table (`specs/002-trail-data-storage-schema`), and what reads/writes them.

## Columns added

| Column | Type | Nullable | Written by | Read by |
|---|---|---|---|---|
| `soil_drainage_rank` | `SMALLINT` | Yes | `server/db/backfill.py::upsert_trail` | `server/app/services/conditions.py::_load_description` |
| `soil_texture_mud_potential` | `SMALLINT` | Yes | Same | Same |
| `soil_texture_group` | `TEXT` | Yes | Same | Same |

Sourced at backfill time from the raw enriched-description JSON's `terrainData.soil.{drainageRank,textureMudPotential,textureGroup}` fields (`server/app/services/trail_info.py::derive_trail_record`) — the same raw fields `data/scripts/model/build_training_table.py` reads for training, satisfying constitution Principle II without either side reimplementing the extraction.

## Why these three and not others

Only fields the live inference path actually consumes and didn't already have a column for (constitution Principle IX). `rock_slip_risk` was already a column (added for a different original purpose, but happens to match what the model needs). `soil_drainage` was already a column but is sourced from a *different* raw field (`terrainData.soil.drainage`, used for the trail-info display) — not reusable for the model's `drainageRank`/`textureMudPotential`/`textureGroup` needs, hence three new columns rather than zero.

## Consumers affected

- **`server/app/services/conditions.py`** (`_load_description`) — reconstructs a dict shaped like the old raw description JSON from a `trails` row (including these three fields nested under `terrainData.soil`), so `feature_flatten.py::flatten_description` (shared with training, Principle II) needed no changes at all.
- **`server/app/services/weather.py`** (`_get_trail_location`) — unaffected by these specific columns (only needs `latitude`/`longitude`, already present), but migrated to read `trails` in the same pass since it had the identical local-file dependency.
- **`aws/lambda/handler.py`** — no direct dependency on these columns; benefits transitively, since the Lambda's existing Postgres connection (for activity data) now also serves description reads with zero additional code.

## Backward compatibility

Nullable, additive columns — existing rows get `NULL` for all three until the next `backfill.py` run repopulates them from source data. No existing query breaks; `_load_description`'s reconstructed dict simply carries `None` for these fields until backfilled, matching how the model's own feature-flattening already treats missing values (per `flatten_terrain`'s defaulting behavior).
