# Data Model: Docker Containerization with S3-Backed Model Loading

This feature introduces no new persisted database entities and does not modify the existing `trails` / `trail_activity` / `trail_geometry` schema (`server/db/migrations/`). Its only "data" surfaces are configuration and one in-memory artifact, described below in place of a traditional entity list.

## Model Artifact (in-memory, per server process)

Represents the deserialized trail-conditions prediction bundle, held only in server process memory after fetch — never written back to disk beyond `boto3`'s internal handling and never persisted to the database.

| Field | Type | Source | Notes |
|---|---|---|---|
| `models` | `dict[str, sklearn estimator]` | joblib-deserialized S3 object | Unchanged from current local-file format; one fitted model per condition key |
| `features` | `list[str]` | joblib-deserialized S3 object | Column order/names the models were trained on; unchanged shape |
| `thresholds` | `dict[str, float]` | joblib-deserialized S3 object | Per-condition classification thresholds; unchanged shape |
| `version` | `str` (ISO date) | **NEW SOURCE**: S3 object's `LastModified` (was: local file mtime) | See research.md §1 |

**Lifecycle**: Fetched at most once per server process (module-level cache in `conditions.py`, existing pattern) → held in memory for the process's lifetime → discarded on process exit. Not versioned or diffed across fetches; a new version requires a server restart (spec Edge Cases).

**Validation rules**:
- Fetch MUST fail loudly (FR-009) if: the S3 object doesn't exist, credentials are invalid/missing, or the downloaded bytes fail to deserialize via `joblib.load` (corrupted artifact).
- No structural validation of `models`/`features`/`thresholds` contents is added beyond what already exists in `conditions.py` today — this feature does not change how the bundle's contents are used, only how the bytes are obtained.

## Service Configuration (environment variables, no persistence)

Represents the set of environment-supplied values that differ between local development and any other environment. Not stored anywhere by the app itself — read once at process startup (or first use, for the model fetch) from the process environment. Full enumeration is in [contracts/env-vars.md](./contracts/env-vars.md).

| Group | Consumed by | Differs per environment? |
|---|---|---|
| Database connection (`DATABASE_URL`) | `server` (`server/db/connection.py`, unchanged) | Yes — points at containerized `db` service locally, a different host elsewhere |
| S3 model location (`MODEL_S3_BUCKET`, `MODEL_S3_KEY`) | `server` (`conditions.py`/`config.py`, new) | Yes — different bucket/key per environment is explicitly required by FR-011 |
| AWS credentials (`AWS_ACCESS_KEY_ID`, `AWS_SECRET_ACCESS_KEY`, `AWS_SESSION_TOKEN`) | `server` (`boto3`'s default chain, new) | Yes locally; typically absent/unset when an IAM role is assumed instead |
| CORS allowed origin (`CLIENT_ORIGIN`) | `server` (`main.py`, new) | Yes — the client's actual served origin per environment |
| Client API base (`VITE_API_BASE`) | `client` (build-time, new) | Yes — baked in at image build time per environment's server address |
| Postgres init (`POSTGRES_USER`, `POSTGRES_PASSWORD`, `POSTGRES_DB`) | `db` service (official Postgres image) | Local-dev only in practice; a hosted Postgres (e.g. a managed DB) wouldn't use this container at all |

No entity here has relationships to model — this section exists to document configuration surface area, not a relational schema.
