# Contract: DynamoDB Stored Prediction Item

The result of successfully processing a Prediction Request, written to `cairns-trail-conditions-predictions`.

## Key schema

- Partition key: `trailId` (String)
- Sort key: `date` (String, ISO `YYYY-MM-DD`)

## Item shape

```json
{
  "trailId": "99887766",
  "date": "2026-09-15",
  "conditions": {
    "bugs": { "probability": 0.12, "predicted": false },
    "flooded": { "probability": 0.04, "predicted": false },
    "icy": { "probability": 0.01, "predicted": false },
    "muddy": { "probability": 0.35, "predicted": false },
    "slippery": { "probability": 0.22, "predicted": false },
    "snow": { "probability": 0.0, "predicted": false }
  },
  "modelVersion": "2026-08-30",
  "confidence": { "reviewCount": 412, "limitedData": false },
  "computedAt": "2026-08-30T14:03:11.482391+00:00"
}
```

`conditions`, `modelVersion`, and `confidence` are exactly `ConditionsResponse`'s fields (`server/app/schemas.py`) — the same shape the synchronous `/conditions` endpoint returns, so a future reader of this table gets an answer indistinguishable from calling that endpoint directly. `computedAt` is the one field this pipeline adds, for its own bookkeeping (not present in the synchronous response).

## Write behavior

- Unconditional `PutItem` (no condition expression) — a write for a `(trailId, date)` key that already has a stored item replaces it entirely. This is deliberate: it's what makes reprocessing a duplicate/retried message safe without a separate idempotency token (spec FR-006/SC-002).
- Numeric values are written as DynamoDB `Decimal`, not native floats — `handler.py` round-trips the Pydantic model's dict through `json.dumps`/`json.loads(parse_float=Decimal)` before calling `put_item`, since boto3's DynamoDB resource API rejects native Python floats.

## Read behavior (not yet built)

No read API is defined in front of this table by this feature (spec.md Assumptions) — a future feature could add one, or the existing FastAPI server could check this table before falling back to synchronous computation. Until then, retrieval is via direct AWS SDK/CLI calls (`aws dynamodb get-item`, per `aws/README.md`'s "Try it" section).
