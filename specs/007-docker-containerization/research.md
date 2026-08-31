# Phase 0 Research: Docker Containerization with S3-Backed Model Loading

## 1. Model version provenance after moving from local mtime to S3

**Decision**: Derive `bundle["version"]` from the S3 object's `LastModified` timestamp (retrieved via the `head_object`/`get_object` response metadata at fetch time), not from the local cache file's mtime.

**Rationale**: `_load_model_bundle` (`server/app/services/conditions.py:51`) currently stamps `version` from `os.path.getmtime(CONDITION_MODELS_PATH)` specifically so it "auto-advances on retrain without a code change." Once the artifact is downloaded into a container's local cache on every fresh start, the local file's mtime becomes "whenever this container downloaded it" — not "whenever the model was actually trained." That silently breaks the provenance signal the field exists for, which matters under Constitution Principle VIII (Honest Uncertainty in Predictions). Capturing S3's `LastModified` at fetch time and storing it in the bundle alongside the cached file preserves the original semantic with no code change to the field's *meaning*, only its source.

**Alternatives considered**:
- *Keep using local cache file mtime*: rejected — reports download time, not training time; actively misleading.
- *Embed a version/timestamp inside the joblib bundle itself at training time*: more robust long-term (survives re-uploads under the same key), but requires changing `data/scripts/model/train_model.py`'s save step, which is out of scope for this feature (spec assumption: model artifact format is unchanged). Left as a future improvement, not blocking.
- *Use S3 object ETag as version*: rejected as primary — ETag is an opaque hash, not human-readable/date-like, and multipart-upload ETags aren't even plain MD5s; `LastModified` matches the existing "date string" shape callers already receive.

## 2. Local caching strategy for the S3-fetched model

**Decision**: Fetch-once-per-process, cached in the existing module-level `_MODEL_BUNDLE` global (already present for the local-disk path today) — no separate on-disk cache file is required. Download the object bytes with `boto3`, `joblib.load` them from an in-memory buffer (`io.BytesIO`), and keep the deserialized bundle in memory for the process lifetime.

**Rationale**: FR-005 only requires avoiding a re-download per request, not surviving process restarts. The existing code already caches the *deserialized* bundle in a module global rather than re-reading the file per request — that pattern already satisfies "cache after first fetch" once the source of the initial load is S3 instead of disk. Introducing a separate on-disk cache file adds a second cache layer (with its own staleness/invalidation questions) for no requirement that asks for it — over-engineering relative to spec scope, which explicitly defers "pick up a new model version" to a server restart (Edge Cases section).

**Alternatives considered**:
- *Download to a local temp file, then `joblib.load` that path*: functionally equivalent but adds unnecessary disk I/O and cleanup; in-memory buffer is simpler and the model bundle is small enough (a handful of scikit-learn estimators) to hold in memory regardless.
- *Persistent on-disk cache surviving container restarts (e.g. a mounted volume for the model file)*: rejected — reintroduces the exact local-path coupling this feature is removing, and conflicts with "no rebuild/mount needed to pick up a new environment's model" (FR-011).

## 3. AWS credential handling in the container

**Decision**: Rely on `boto3`'s standard credential resolution chain — environment variables (`AWS_ACCESS_KEY_ID`, `AWS_SECRET_ACCESS_KEY`, optionally `AWS_SESSION_TOKEN`) for local development, and an assumed IAM role (instance/task role, no explicit keys) when running on AWS infrastructure. Bucket and key are supplied via app-specific env vars (`MODEL_S3_BUCKET`, `MODEL_S3_KEY`), not baked into image or code.

**Rationale**: This is exactly the pattern the spec's Assumptions section already commits to, it requires zero custom credential-management code, and it's the documented, supported `boto3` default — introducing a custom credentials file or secrets mechanism would be scope creep for a feature that only needs to read one object.

**Alternatives considered**:
- *Bake credentials into the image*: rejected outright — violates FR-006 and is a standing secret-leak risk in image layers/registries.
- *Mount an AWS credentials file as a volume*: viable for some setups but adds local-dev-only file management with no benefit over env vars for a single-object read use case; env vars keep local dev and hosted deployment using the identical mechanism (just different values), matching FR-011.

## 4. Client → server connectivity across container boundaries

**Decision**: Make the client's `API_BASE` (`client/src/api/trails.ts:6`, currently hardcoded to `http://localhost:8000`) a Vite build-time environment variable (`VITE_API_BASE`, defaulting to `http://localhost:8000` when unset so existing non-Docker local dev is unaffected). Add the client's serving origin to the server's CORS `allow_origins` list (`server/app/main.py`) via an env var rather than a second hardcoded string, since the client is no longer guaranteed to be reachable at the Vite dev server's `localhost:5173` origin once it's built and served as static assets from its own container.

**Rationale**: `API_BASE` and CORS origins are the only two hardcoded cross-service assumptions in the current code; both must become configurable for FR-007 and FR-011 (same image, different environment, no code change) to actually hold. Vite's `import.meta.env.VITE_*` convention is the standard, zero-dependency way to inject a build-time value into a static Vite build.

**Alternatives considered**:
- *Runtime config fetched by the client (e.g. a `/config.json` the server serves)*: more flexible (same static build could target different servers without rebuilding) but is a larger change than this feature's scope calls for; the spec's own assumption is "the same build can point at different server deployments" via environment variables, which build-time env vars already satisfy per SC-003. Deferred as a future improvement if runtime (not build-time) reconfiguration is ever needed.
- *Leave CORS hardcoded to `localhost:5173`*: rejected — the containerized client is not served from Vite's dev server, so requests from the client's actual container origin would be silently blocked by CORS, breaking User Story 1's acceptance criteria.

## 5. Postgres container and existing migrations

**Decision**: Use the official `postgres:16` image with a named volume for `/var/lib/postgresql/data`; continue applying `server/db/migrations/*.sql` the same way they're applied today (manually, e.g. `psql -f`, per `server/README.md`) but pointed at the containerized instance — this feature does not add a migration-runner tool.

**Rationale**: Spec Assumptions explicitly scope this out ("this feature does not change how migrations are authored or ordered, only how/where Postgres itself runs"). The existing migration files are plain, ordered `.sql` files with no tracking table or runner script today; inventing one now would be an unrelated scope expansion. `POSTGRES_USER`/`POSTGRES_PASSWORD`/`POSTGRES_DB` env vars on the `db` service are set to match the `DATABASE_URL` the `server` service is given, keeping the existing `psycopg2.connect(DATABASE_URL)` call in `server/db/connection.py` completely unchanged.

**Alternatives considered**:
- *Auto-apply migrations via Postgres's `docker-entrypoint-initdb.d` mechanism*: tempting, but that mechanism only runs on first initialization of an empty data directory, not on every start — it would silently stop applying new migration files the moment the volume already exists, giving a false sense of "migrations are handled." Rejected as misleading given no migration-tracking table exists to make it idempotent.
- *Introduce Alembic or a similar migration tool*: real long-term improvement, but unrelated to containerization and a much larger change than this feature's scope.

## 6. Client static-asset serving

**Decision**: Multi-stage `client/Dockerfile` — a `node:20-slim` (or current LTS) build stage running `npm ci && npm run build`, then a lightweight `nginx:alpine` stage that only copies the resulting `dist/` output and serves it.

**Rationale**: This is the standard, minimal-image-size pattern for shipping a Vite/React static build; it keeps the Node toolchain and `node_modules` out of the final runtime image entirely. `npm run build` (already defined in `client/package.json`) is reused unmodified.

**Alternatives considered**:
- *Serve via `vite preview` in the runtime container*: keeps Node + all dev dependencies in the final image for no benefit — `vite preview` is documented as a preview tool, not a production server.
- *Serve via `npm run dev` in the container*: rejected — that's a dev server with HMR/websocket overhead, not appropriate for anything beyond live-editing.
