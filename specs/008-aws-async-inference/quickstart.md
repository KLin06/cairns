# Quickstart: Validate Async Serverless Model Inference at Scale

This feature has two independently-verifiable parts. Part 1 has already been run and its results are recorded below; Part 2 requires a real AWS account and hasn't been executed as part of writing this plan (deploying is a deliberate operator action, not something done automatically — see spec.md's Scope Note).

## Part 1 — Server-side migration (already verified)

Validates that moving `_load_description`/`_get_trail_location` off local files and onto Postgres (the follow-on migration this feature required) didn't break the existing synchronous behavior.

```bash
# From server/, with Docker running:
docker run -d --name cairns-test-pg -e POSTGRES_USER=test -e POSTGRES_PASSWORD=test -e POSTGRES_DB=test -p 5433:5432 postgres:16
TEST_DATABASE_URL="postgresql://test:test@localhost:5433/test" venv/Scripts/python -m pytest -q
docker rm -f cairns-test-pg
```

**Result when this was run**: 38/38 passed (up from 30 passed/9 skipped before this feature — `test_conditions.py`/`test_weather.py` now exercise the DB-backed path for real, not a stand-in file, and a pre-existing gap in `conftest.py` — only migration 0001 was ever applied to the test schema — was fixed as part of this work).

## Part 2 — AWS deployment (not yet run against a real account)

Follow [aws/README.md](../../aws/README.md) end to end:

1. **Prerequisites** — AWS credentials, Docker, an S3 bucket with `condition_models.joblib` uploaded, `cdk bootstrap`.
2. **Deploy** — `cdk deploy -c modelBucketName=... -c alertEmail=...`. Confirmed via `cdk synth` and a real `docker build` of the Lambda image that this produces a valid, buildable deployment: VPC, RDS Postgres instance (`db.t3.micro` — see `aws/SYSTEM_DESIGN.md` §6.5 for why not Aurora), the security-group ingress rule from the Lambda to Postgres, SQS queue + DLQ, DynamoDB table, the Lambda function with least-privilege IAM grants, SNS topic, and two CloudWatch alarms — see `aws/README.md`'s "What's here" / this plan's Project Structure for the full resource inventory.
3. **Populate the database** — run the existing migrations (0001-0004) and `server/db/backfill.py` against the new RDS endpoint (`aws/README.md`'s "Populate the database" section).
4. **Try it** — submit a message via `aws sqs send-message`, confirm a `GetItem` on the DynamoDB table returns a computed prediction (validates User Story 1 + 2 / SC-002).
5. **Failure path** — submit a message with an invalid date or a `trailId` with no `trails` row, confirm it reaches the dead-letter queue after 5 retries and triggers the SNS email alert (validates User Story 3 / SC-003/SC-007).
6. **Burst behavior** (SC-001) — submit ≥1,000 messages (e.g. via `aws sqs send-message-batch` in a loop) and confirm they drain within a few minutes without manual intervention.

Steps 4-6 require a live AWS deployment and haven't been executed — they're the acceptance checks a future session (or the user, directly) would run once `cdk deploy` has actually been invoked against a real account.

## Cross-references

- Full resource inventory and cost notes: [aws/README.md](../../aws/README.md)
- Full design reasoning: [aws/SYSTEM_DESIGN.md](../../aws/SYSTEM_DESIGN.md)
- Message/item/schema contracts: [contracts/](./contracts/)
