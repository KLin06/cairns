# Quickstart: Validate Docker Containerization + S3 Model Loading

Validates the acceptance scenarios in [spec.md](./spec.md) end-to-end. Run after implementation (post `/speckit-implement`), not as part of planning.

## Prerequisites

- Docker Engine + Docker Compose installed.
- An S3 bucket with a valid `condition_models.joblib` object uploaded (see [contracts/s3-model-object.md](./contracts/s3-model-object.md) for the expected format) — reuse the app's existing `data/datasets/models/condition_models.joblib` for this.
- AWS credentials with `s3:GetObject` on that bucket/key (an IAM user's access key for local dev is simplest).
- A copy of `.env.example` → `.env` at the repo root with real values filled in for: `DATABASE_URL`/`POSTGRES_*`, `MODEL_S3_BUCKET`, `MODEL_S3_KEY`, `AWS_ACCESS_KEY_ID`, `AWS_SECRET_ACCESS_KEY`, `AWS_REGION`, `CLIENT_ORIGIN`. Full list: [contracts/env-vars.md](./contracts/env-vars.md).

## Scenario 1 — Bring up the full stack (User Story 1)

```bash
docker compose up --build
```

**Expected**: three containers start (`db`, `server`, `client`) with no errors. Open the client's served URL (e.g. `http://localhost:8080`) in a browser — the trail map and list load, confirming the client successfully reached the server and the server successfully reached Postgres.

**Persistence check**: `docker compose down` (no `-v`), then `docker compose up` again — previously visible trail data is still present, confirming FR-002 / SC-005.

## Scenario 2 — Server fetches the model from S3 (User Story 2)

```bash
curl http://localhost:8000/health
curl "http://localhost:8000/trails/{a_known_trail_id}/conditions?date=YYYY-MM-DD"
```

(substitute a real trail ID from your backfilled data and a date within the forecast horizon)

**Expected**: the conditions request succeeds and returns predictions with a `modelVersion` field. Check server logs (`docker compose logs server`) to confirm a single S3 fetch occurred, not a read from a local `condition_models.joblib` file (there should be none on the image — confirm with `docker compose exec server ls /app` or equivalent, showing no local model file baked in).

**Caching check**: issue a second conditions request (any trail/date) and confirm via logs that no second S3 fetch occurs — the process reused its in-memory cached bundle (FR-005 / SC-004).

**Failure-mode check**: temporarily set `MODEL_S3_KEY` to a nonexistent key, restart the `server` service, and confirm the conditions endpoint returns a clear error (not a hang or a silently-empty prediction) — validates FR-009.

## Scenario 3 — Environment portability (User Story 3)

Without changing any source file or rebuilding images, start a second stack (or the same images against different `.env` values) pointing `DATABASE_URL` at a different Postgres instance and `MODEL_S3_BUCKET`/`MODEL_S3_KEY` at a different S3 location.

**Expected**: the server connects to the new database and serves predictions from the new model location — confirming SC-003 / FR-011. Confirm no container in this stack corresponds to the `data/` training pipeline (`docker compose ps` shows only `db`, `server`, `client`).

## Config-validation check (FR-010)

Start the stack with one required variable removed (e.g. unset `MODEL_S3_BUCKET`) and confirm the `server` service fails fast at startup with a clear error naming the missing variable, rather than starting and failing later on first request.
