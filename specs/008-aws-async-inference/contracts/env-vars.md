# Contract: Environment Variables (`cairns-prediction-worker` Lambda)

Extends (does not replace) [specs/007-docker-containerization/contracts/env-vars.md](../../007-docker-containerization/contracts/env-vars.md)'s server contract — the Lambda reuses `server/app`/`server/db` directly, so anything that module already reads from the environment (e.g. `DATABASE_URL`, consumed by `db/connection.py`) still applies; this file only covers what's specific to the Lambda's own deployment.

| Variable | Set by | Purpose |
|---|---|---|
| `MODEL_S3_BUCKET` | CDK (`modelBucketName` context) | Same contract as spec 007 — bucket holding `condition_models.joblib` |
| `MODEL_S3_KEY` | CDK (`modelS3Key` context, default `condition_models.joblib`) | Same contract as spec 007 |
| `PREDICTIONS_TABLE_NAME` | CDK (`predictionsTable.tableName`) | Which DynamoDB table `handler.py` writes results to |
| `DB_CREDENTIALS_SECRET_ARN` | CDK (`database.secret.secretArn`) | Secrets Manager secret containing `{username, password}` for the RDS instance — read once at cold start |
| `DB_HOST` | CDK (`database.clusterEndpoint.hostname`) | Not secret — passed as a plain value rather than duplicated into the secret |
| `DB_PORT` | CDK (`database.clusterEndpoint.port`) | Same as `DB_HOST` |
| `DB_NAME` | CDK (hardcoded `"cairns"`, matching `defaultDatabaseName`) | Same as `DB_HOST` |

`handler.py` combines `DB_CREDENTIALS_SECRET_ARN`'s username/password with `DB_HOST`/`DB_PORT`/`DB_NAME` to build `DATABASE_URL` (URL-encoding the credential values defensively) and sets it in `os.environ` before `server/db/connection.py`'s `get_connection()` is ever called — from that point on, the reused server code has no idea it's running in Lambda rather than the Docker container from spec 007.

## Not covered here

- `AWS_REGION` — a Lambda-reserved environment variable name, set automatically by the runtime; never set explicitly by this stack.
- Anything from `data/.env` or the client's `VITE_API_BASE` — unrelated to this feature.
