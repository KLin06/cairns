# Feature Specification: Docker Containerization with S3-Backed Model Loading

**Feature Branch**: `007-docker-containerization`

**Created**: 2026-08-29

**Status**: Draft

**Input**: User description: "Containerize the app with Docker for local dev and deployment: a postgres service, a FastAPI server service (server/), and a client service (client/, built and served as static assets). The server's ML model artifact (currently loaded from data/datasets/models/condition_models.joblib via server/app/services/conditions.py's _load_model_bundle, path from server/app/config.py's CONDITION_MODELS_PATH) is moving to S3, so the server container must fetch the model from S3 (via boto3, using env vars for bucket/key and AWS credentials/IAM role) instead of reading it off a local/mounted path, caching it locally after first fetch. The data/ ML training pipeline is NOT part of the always-on containerized stack - it stays a separate one-off/manual process outside docker-compose. Scope: docker-compose.yml for local dev, Dockerfiles for server and client, env var configuration for Postgres connection and S3 model location/credentials, and the model-loading code change to support fetching from S3 with local caching instead of only reading a local path."

## User Scenarios & Testing *(mandatory)*

### User Story 1 - Bring up the full stack with one command (Priority: P1)

A developer who has just cloned the repository (or is returning to it after time away) wants to run the entire application — database, API server, and client — without manually installing Postgres, Python dependencies, and Node dependencies on their own machine, and without hunting down or hand-configuring a local copy of the trained model.

**Why this priority**: This is the core value of containerizing the app at all. Without it, there is no reduction in setup friction and the rest of the scope has no purpose.

**Independent Test**: On a clean checkout, with only Docker installed and valid AWS credentials/S3 location supplied via environment variables, running a single documented command brings up all three services and the client is reachable in a browser with the map and trail data loading correctly.

**Acceptance Scenarios**:

1. **Given** a clean checkout of the repository and Docker installed, **When** the developer runs the documented startup command with required environment variables set, **Then** a database service, an API server service, and a client service all start successfully and the client can be opened in a browser.
2. **Given** the stack is running for the first time, **When** the API server starts, **Then** it connects to the containerized database using connection details supplied via environment variables, without any code change required to point at a different database host.
3. **Given** the stack is stopped and restarted, **When** the developer runs the startup command again, **Then** previously stored database data is still present (data persists across restarts).

---

### User Story 2 - Server loads the prediction model from S3 (Priority: P1)

A developer or operator wants the API server to obtain its trail-conditions prediction model from S3 rather than requiring the model file to already exist on the machine or be baked into the container image, so that publishing a newly trained model does not require rebuilding or redeploying the server.

**Why this priority**: This is the specific architectural shift motivating this feature now (the model is moving to S3) and is a prerequisite for the containerized server to serve conditions predictions at all in an environment where no local model file exists.

**Independent Test**: With no model file present anywhere on the server container's filesystem at image-build time, and valid S3 location/credentials supplied via environment variables, a request to the conditions-prediction endpoint succeeds and returns a prediction after the server fetches the model from S3.

**Acceptance Scenarios**:

1. **Given** the server container has no locally-mounted or pre-baked model file, **When** the server needs the model to answer a conditions-prediction request, **Then** it downloads the model artifact from the S3 location specified via environment variables and uses it to produce the prediction.
2. **Given** the server has already fetched the model once since starting, **When** a subsequent conditions-prediction request arrives, **Then** the server reuses its locally cached copy instead of re-downloading from S3.
3. **Given** S3 credentials or the configured bucket/key are invalid or unreachable, **When** the server attempts to fetch the model, **Then** it fails with a clear, logged error rather than silently serving stale or fabricated predictions.

---

### User Story 3 - Deploy the containerized app to a hosting environment (Priority: P2)

An operator wants to take the same container images used in local development and run them in a hosting environment (e.g. a cloud VM or container host), supplying production values for database connection and S3/model configuration through environment variables rather than code changes.

**Why this priority**: Local dev parity is necessary but the eventual goal is a deployable artifact; this story confirms the same images/config approach extends beyond a developer's laptop. It is lower priority than P1 stories because local dev must work first, and a specific hosting target is not yet chosen.

**Independent Test**: The server and client images built for local development can be started in a separate environment (a second machine, or a fresh set of containers) pointed at a different Postgres instance and a different S3 bucket/key purely by changing environment variables, with no source code or image rebuild required for that reconfiguration.

**Acceptance Scenarios**:

1. **Given** built server and client images, **When** they are run in a new environment with a different set of environment variables (database host, S3 bucket/key, AWS credentials), **Then** the application connects to the new database and fetches the model from the new S3 location without modification to the image or source code.
2. **Given** the training pipeline under `data/` is not part of the containerized stack, **When** the containerized stack is deployed, **Then** no training-pipeline process is started or expected to run as part of that deployment.

---

### Edge Cases

- What happens when the S3 bucket/key is reachable but the object at that key is missing or corrupted (fails to deserialize as a model bundle)? The server MUST fail the affected request(s)/startup step with a clear error rather than serving a partially-loaded or default model.
- What happens when the model in S3 is updated to a new version while the server is already running with a cached copy? Per this feature's scope, the server is not required to auto-detect the update; picking up a new model version requires a server restart (re-fetch on next cold start). Live hot-reloading of an updated model is out of scope.
- What happens when the Postgres container's data volume does not yet exist (very first startup)? The database service MUST initialize a fresh, empty database and the server MUST be able to apply/expect its existing schema against it.
- What happens if required environment variables (DB connection, S3 bucket/key, AWS credentials) are missing entirely? Each service MUST fail fast at startup with a clear error identifying the missing configuration, rather than starting in a partially-configured state.
- What happens to the `data/` training pipeline's own dependencies and scripts when the app is containerized? They remain runnable manually/outside the containerized stack (e.g. run directly on a developer machine or as a separate one-off job) and are explicitly not started, scheduled, or health-checked by the containerized stack.

## Requirements *(mandatory)*

### Functional Requirements

- **FR-001**: The system MUST provide a way to start a database service, an API server service, and a client service together with a single documented command, for local development.
- **FR-002**: The database service MUST persist its data across stops/restarts of the stack.
- **FR-003**: The API server service MUST obtain its database connection details (host, port, credentials, database name) from environment variables rather than hardcoded values.
- **FR-004**: The API server MUST obtain the trail-conditions prediction model from an S3 location specified via environment variables, rather than requiring the model file to be present on the local filesystem at image-build time or via a manually-mounted path.
- **FR-005**: The API server MUST cache the model locally after fetching it from S3 for the lifetime of the running server process, and MUST NOT re-fetch it from S3 on every prediction request.
- **FR-006**: The API server MUST authenticate to S3 using credentials supplied via environment variables and/or an assumed IAM role, without hardcoded credentials in source code or images.
- **FR-007**: The client service MUST be built and served as static assets, reachable via a browser, and configured (e.g. API base URL) via environment variables so the same build can point at different server deployments.
- **FR-008**: The system MUST NOT include the `data/` training pipeline as a service that is started, scheduled, or health-checked as part of the containerized stack.
- **FR-009**: The API server MUST fail fast with a clear, logged error at startup or at first prediction request (whichever the model-loading path triggers on) if it cannot obtain a valid model — whether due to unreachable S3, invalid credentials, a missing object, or a corrupted/unreadable artifact.
- **FR-010**: Each containerized service MUST fail fast with a clear error identifying any missing required configuration (database connection details, S3 bucket/key, AWS credentials) rather than starting in a partially-configured or silently-degraded state.
- **FR-011**: The same container images MUST be runnable in a different environment (different database host, different S3 bucket/key/credentials) purely through environment variable changes, without requiring a rebuild or source code change.

### Key Entities

- **Model Artifact**: The trained trail-conditions prediction bundle (models, feature list, thresholds, version) currently stored as a local `.joblib` file and moving to an S3 object; identified by a configurable bucket and key, and cached locally by the server process after first retrieval.
- **Service Configuration**: The set of environment-supplied values (database connection details, S3 bucket/key, AWS credentials/role, client API base URL) that differ between local development and any other hosting environment without requiring code or image changes.

## Success Criteria *(mandatory)*

### Measurable Outcomes

- **SC-001**: A developer with a clean checkout and Docker installed can get the full stack (database, server, client) running and reachable in a browser in under 10 minutes, without manually installing Postgres, Python, or Node dependencies on their host machine.
- **SC-002**: Zero application source files or container images need to change when the model artifact in S3 is replaced with a newer version — only a server restart is required to pick it up.
- **SC-003**: The same built images can be pointed at a new database and a new S3 model location in a different environment using only environment variable changes, with no image rebuild.
- **SC-004**: After the first successful model fetch, repeated conditions-prediction requests do not trigger additional S3 downloads for the remainder of that server process's lifetime.
- **SC-005**: Restarting the containerized stack does not lose previously stored database data.

## Assumptions

- AWS credentials for S3 access will be supplied to the server container via environment variables (access key/secret) for local development and/or via an assumed IAM role in a hosted environment; this feature does not implement a new credential-management system beyond what boto3's standard credential chain already supports.
- The model artifact format itself (a joblib-serialized bundle of `{models, features, thresholds, version}`) is unchanged by this feature — only where it is fetched from changes, not its internal structure or how `conditions.py` consumes it.
- "Local development" means running via Docker Compose on a single developer machine; a specific production hosting target (e.g. a specific cloud provider or orchestrator) has not yet been chosen, so this feature targets environment-variable-driven portability rather than a specific deployment platform's manifests.
- The client is served as static built assets (not a Node server process) behind whatever web server the client's container image runs, consistent with the existing Vite-based build (`npm run build`).
- The existing database schema/migrations under `server/db/migrations` continue to be applied the same way (manually or via an existing script) against the containerized Postgres instance; this feature does not change how migrations are authored or ordered, only how/where Postgres itself runs.
- Model re-fetch on update is handled by restarting the server process (cold start re-fetches); no live file-watching or hot-reload mechanism is introduced by this feature.
