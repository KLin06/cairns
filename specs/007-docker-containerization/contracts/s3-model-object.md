# Contract: S3 Model Object

Defines what the server expects to find at `s3://{MODEL_S3_BUCKET}/{MODEL_S3_KEY}` (see [env-vars.md](./env-vars.md)).

## Object format

- **Serialization**: `joblib`-serialized Python object (identical format to today's local `condition_models.joblib`) — this feature does not change the artifact's internal format, only its storage location.
- **Structure**: a `dict` with exactly these keys, matching what `data/scripts/model/train_model.py` already produces and what `server/app/services/conditions.py::_load_model_bundle` already expects:
  - `models`: `dict[str, fitted sklearn estimator]`
  - `features`: `list[str]`
  - `thresholds`: `dict[str, float]`

## Server's read contract

- The server treats this object as **read-only** — it never writes to S3.
- The server fetches it via `boto3`'s `get_object` (or equivalent), reads the body into memory, and `joblib.load`s it from an in-memory buffer (no dependency on the object being downloaded to a specific local path).
- The server additionally reads the object's `LastModified` timestamp from the same fetch response and stores it as `bundle["version"]` (an ISO date string) — this is metadata the S3 API returns alongside the object body, not a separate field of the joblib payload itself.
- The server fetches this object at most once per process lifetime (first request that needs the model, or at startup — implementation's choice) and caches the deserialized result in memory for all subsequent requests.

## Failure modes the server MUST handle (FR-009)

| Condition | Required behavior |
|---|---|
| Object does not exist at the configured bucket/key | Fail the triggering request/startup step with a clear, logged error identifying the missing object |
| S3 unreachable / network error | Fail with a clear, logged error; no silent fallback to a stale or default model |
| Credentials invalid or lack permission (`AccessDenied`) | Fail with a clear, logged error distinguishing this from a "not found" case where feasible |
| Object exists but `joblib.load` fails (corrupted/unexpected format) | Fail with a clear, logged error — do not serve a partially-loaded model |

## Publishing the object (out of scope for this feature)

How the model gets *into* S3 (a manual upload after training, or an automated step at the end of `data/scripts/model/train_model.py`) is not part of this feature's scope — the spec's Assumptions section treats "the model is moving to S3" as a given precondition. This contract only defines what the server reads.
