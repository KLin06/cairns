# Contract: SQS Prediction Request Message

The body of a message submitted to the `cairns-prediction-requests` queue.

## Format

```json
{ "trailId": "99887766", "date": "2026-09-15" }
```

| Field | Type | Required | Notes |
|---|---|---|---|
| `trailId` | string | Yes | Same identifier the synchronous `/trails/{trail_id}/conditions` endpoint accepts |
| `date` | string | Yes | ISO `YYYY-MM-DD`. Must be within the model's valid forecast horizon — same rule the synchronous endpoint enforces (spec 001's `MAX_FORECAST_DAYS`) |

## Producer expectations

- Standard queue, not FIFO — no ordering or exactly-once guarantee, and none is needed (see [research.md](../research.md) §1 note on idempotency).
- A producer may submit the same `(trailId, date)` more than once; the worker's processing is idempotent (an unconditional `PutItem` overwrite), so duplicate submissions are harmless, not an error condition to avoid.
- There is currently no automated producer (no scheduled batch job) — messages are submitted manually (`aws sqs send-message`, per `aws/README.md`) or by whatever external caller an operator wires up. Building an automated producer was explicitly deferred (out of scope for this iteration).

## Consumer behavior

- Delivered to the `cairns-prediction-worker` Lambda in batches of up to 5 (`batchSize` in `inference-stack.ts`).
- A message that fails processing is reported via `reportBatchItemFailures` and redelivered (subject to the queue's visibility timeout) up to 5 times total before landing in the dead-letter queue.
