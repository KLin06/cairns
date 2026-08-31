# Contract: Environment Variables

This is the full set of environment variables the containerized stack accepts. Every service MUST fail fast (FR-010) at startup with a clear error naming the missing variable if a required one is absent — no silent defaulting for required values.

## `server` service

| Variable | Required | Example (local dev) | Purpose |
|---|---|---|---|
| `DATABASE_URL` | Yes | `postgresql://cairns:cairns@db:5432/cairns` | Passed straight to `psycopg2.connect()` in `server/db/connection.py` (unchanged) |
| `MODEL_S3_BUCKET` | Yes | `cairns-models` | S3 bucket holding `condition_models.joblib` |
| `MODEL_S3_KEY` | Yes | `condition_models.joblib` | Object key within the bucket |
| `AWS_ACCESS_KEY_ID` | Only if not using an assumed IAM role | — | Standard `boto3` credential var; unset in environments using an instance/task role |
| `AWS_SECRET_ACCESS_KEY` | Only if not using an assumed IAM role | — | Standard `boto3` credential var |
| `AWS_SESSION_TOKEN` | No | — | Only needed for temporary/STS credentials |
| `AWS_REGION` (or `AWS_DEFAULT_REGION`) | Yes | `us-east-1` | Region of the S3 bucket |
| `CLIENT_ORIGIN` | Yes | `http://localhost:8080` | Added to `CORSMiddleware(allow_origins=[...])` in `server/app/main.py` so the containerized client's origin is permitted |

## `client` service (build-time only — consumed by `vite build`, not present at container runtime)

| Variable | Required | Example (local dev) | Purpose |
|---|---|---|---|
| `VITE_API_BASE` | No (defaults to `http://localhost:8000`) | `http://localhost:8000` | Baked into the static build as `import.meta.env.VITE_API_BASE`, replacing the hardcoded value in `client/src/api/trails.ts` |

## `db` service (official `postgres` image's own variables)

| Variable | Required | Example (local dev) | Purpose |
|---|---|---|---|
| `POSTGRES_USER` | Yes | `cairns` | Must match the user embedded in `server`'s `DATABASE_URL` |
| `POSTGRES_PASSWORD` | Yes | `cairns` | Must match the password embedded in `server`'s `DATABASE_URL` |
| `POSTGRES_DB` | Yes | `cairns` | Must match the database name embedded in `server`'s `DATABASE_URL` |

## Not covered by this contract

- `TEST_DATABASE_URL` (used by `server/tests/conftest.py`) — test-only, unrelated to the containerized runtime stack, unchanged by this feature.
- Anything under `data/.env` (`ALLTRAILS_SESSION_COOKIE`) — the `data/` pipeline is explicitly outside the containerized stack (FR-008).
