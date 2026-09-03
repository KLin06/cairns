# Data Model: Async Serverless Model Inference at Scale

## Prediction Request (transient — SQS message)

Exists only in the queue between submission and processing; not persisted anywhere after that. See [contracts/sqs-message.md](./contracts/sqs-message.md) for the exact JSON shape.

| Field | Type | Notes |
|---|---|---|
| `trailId` | string | Same identifier the synchronous `/trails/{trail_id}/conditions` endpoint accepts |
| `date` | string (ISO date) | Must be within the model's valid forecast horizon (same rule as the synchronous endpoint) |

## Stored Prediction (durable — DynamoDB item)

`cairns-trail-conditions-predictions` table, partition key `trailId` + sort key `date`. This is `ConditionsResponse` (`server/app/schemas.py`) plus one bookkeeping field — not a shape invented for this pipeline. See [contracts/dynamodb-item.md](./contracts/dynamodb-item.md).

| Field | Type | Source |
|---|---|---|
| `trailId` | string | Request |
| `date` | string (ISO date) | Request |
| `conditions` | map | `ConditionsResponse.conditions` — per-condition `{probability, predicted}` |
| `modelVersion` | string | `ConditionsResponse.modelVersion` |
| `confidence` | map | `ConditionsResponse.confidence` — `{reviewCount, limitedData}` |
| `computedAt` | string (ISO datetime) | Set by `handler.py` at write time — not part of the synchronous endpoint's response shape, added for this pipeline's own bookkeeping |

**Validation/lifecycle rules**: `PutItem` with no condition expression — an unconditional overwrite, which is what makes reprocessing the same (trailId, date) key naturally idempotent (spec FR-006/SC-002) rather than requiring a dedup token.

## Failed Request Record (SQS dead-letter message)

Not a separate schema — a Prediction Request message that exhausted `maxReceiveCount` retries, moved automatically to the DLQ by SQS's own redrive policy. Diagnosable via the message body (the original request) plus CloudWatch Logs for the Lambda invocations that attempted it (correlated by timestamp/trailId/date — there is no explicit failure-reason field attached to the DLQ message itself, per the deliberate simplification in [research.md](./research.md) §6).

## Trail Record — schema addition (persistent — Postgres, `trails` table)

Not a new entity — an addition to the existing `trails` table (`specs/002-trail-data-storage-schema`), needed because this feature's Lambda (and, per the follow-on migration, the synchronous server too) reads trail data from Postgres rather than a local file. Added by [server/db/migrations/0004_add_model_terrain_features.sql](../../server/db/migrations/0004_add_model_terrain_features.sql); full contract in [contracts/trails-schema-addition.md](./contracts/trails-schema-addition.md).

| New column | Type | Source (raw pipeline field) | Why it wasn't already a column |
|---|---|---|---|
| `soil_drainage_rank` | SMALLINT, nullable | `terrainData.soil.drainageRank` | The existing `soil_drainage` column is sourced from a *different* field (`terrainData.soil.drainage`, for display) — the model needs the ordinal rank, not the same value |
| `soil_texture_mud_potential` | SMALLINT, nullable | `terrainData.soil.textureMudPotential` | Never previously extracted — the display-oriented `derive_trail_record()` had no use for it before this feature |
| `soil_texture_group` | TEXT, nullable | `terrainData.soil.textureGroup` | Same as above |

These are fixed-shape scalar fields (an ordinal rank, a small integer, a short text label) — real typed columns per constitution Principle X, not JSONB.

## Service Configuration (environment variables / Secrets Manager — no persistence)

Full enumeration in [contracts/env-vars.md](./contracts/env-vars.md). Summary of what differs from spec 007's server-side configuration:

| Group | Consumed by | Notes |
|---|---|---|
| S3 model location (`MODEL_S3_BUCKET`, `MODEL_S3_KEY`) | Lambda (reused from spec 007's contract) | Same S3 object, same env var names |
| DynamoDB table name (`PREDICTIONS_TABLE_NAME`) | Lambda | New — this feature's own table |
| Database connection (`DB_CREDENTIALS_SECRET_ARN`, `DB_HOST`, `DB_PORT`, `DB_NAME`) | Lambda | New — combined into `DATABASE_URL` at cold start (`handler.py`), consumed downstream by the unmodified `server/db/connection.py` |
| Alert destination (`alertEmail` CDK context) | SNS subscription | New — not a Lambda env var, a deploy-time parameter |
