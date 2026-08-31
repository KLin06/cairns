---

description: "Task list template for feature implementation"
---

# Tasks: Docker Containerization with S3-Backed Model Loading

**Input**: Design documents from `/specs/007-docker-containerization/`

**Prerequisites**: [plan.md](./plan.md), [spec.md](./spec.md), [research.md](./research.md), [data-model.md](./data-model.md), [contracts/](./contracts/), [quickstart.md](./quickstart.md)

**Tests**: Not explicitly requested in the spec. One narrow exception is included (T014) because plan.md's Testing section already commits to it: a unit test for the new S3 fetch/cache logic, since that logic has real failure modes (FR-009) worth pinning down with a mocked-`boto3` test rather than only manual quickstart verification.

**Organization**: Tasks are grouped by user story (US1/US2/US3, matching [spec.md](./spec.md) priorities P1/P1/P2) to enable independent implementation and testing of each story.

## Format: `[ID] [P?] [Story] Description`

- **[P]**: Can run in parallel (different files, no dependencies)
- **[Story]**: Which user story this task belongs to (US1, US2, US3)

## Path Conventions

This is the existing `client/` + `server/` web-app split (see [plan.md](./plan.md) Project Structure) plus new root-level infra files. All paths below are repo-root-relative.

---

## Phase 1: Setup (Shared Infrastructure)

**Purpose**: Scaffolding needed before any Dockerfile or code change.

- [X] T001 [P] Create `server/.dockerignore` (exclude `venv/`, `__pycache__/`, `.env`, `tests/`)
- [X] T002 [P] Create `client/.dockerignore` (exclude `node_modules/`, `dist/`)
- [X] T003 [P] Add `boto3` to `server/requirements.txt`
- [X] T004 Create `.env.example` at repo root documenting every variable from [contracts/env-vars.md](./contracts/env-vars.md) (with placeholder, non-secret example values)

**Checkpoint**: Repo has the scaffolding files every later task references.

---

## Phase 2: Foundational (Blocking Prerequisites)

**Purpose**: The two Dockerfiles and the cross-service CORS fix that every user story's containers depend on.

**⚠️ CRITICAL**: No user story task can be verified in a container until this phase is complete.

- [X] T005 [P] Create `server/Dockerfile` — Python base image, `COPY requirements.txt` + `pip install`, copy `app/` and `db/`, run `uvicorn app.main:app --host 0.0.0.0 --port 8000` (per [plan.md](./plan.md) Project Structure)
- [X] T006 [P] Create `client/Dockerfile` — multi-stage: `node:20-slim` stage runs `npm ci && npm run build`, final `nginx:alpine` stage copies `dist/` and serves it (per [research.md](./research.md) §6)
- [X] T007 Add `CLIENT_ORIGIN` env-var-driven CORS origin to `server/app/main.py`'s `CORSMiddleware(allow_origins=[...])` (currently hardcoded to `http://localhost:5173`; must include the containerized client's actual origin per [research.md](./research.md) §4)

**Checkpoint**: Both images build standalone (`docker build`) and the server's CORS config is environment-driven. User story implementation can now begin.

---

## Phase 3: User Story 1 - Bring up the full stack with one command (Priority: P1) 🎯 MVP

**Goal**: A developer with a clean checkout and Docker can run one command and reach a working client backed by a containerized database and API server.

**Independent Test**: Run the compose command from a clean checkout with only DB-related env vars set (no S3/model config needed — the trail-list/trail-info endpoints this story exercises don't touch the model per Constitution Principle I); confirm all three containers start and the client's map/trail list loads in a browser.

### Implementation for User Story 1

- [X] T008 [US1] Create `docker-compose.yml` at repo root with three services — `db` (`postgres:16`, `POSTGRES_USER`/`POSTGRES_PASSWORD`/`POSTGRES_DB` from `.env`, named volume `db_data:/var/lib/postgresql/data`), `server` (build from `server/Dockerfile`, `DATABASE_URL`/`CLIENT_ORIGIN` from `.env`, depends_on `db`, published port 8000), `client` (build from `client/Dockerfile`, published port 8080) — per [data-model.md](./data-model.md) Service Configuration table. Also mounts `./data/datasets:/data/datasets:ro` into `server` — discovered during implementation that `app/config.py`'s `DATASETS_DIR` (used by trail-info/activity/geometry/weather, not just the model) still reads straight off disk and needs a path inside the container; `server/Dockerfile`'s `WORKDIR /srv` was chosen specifically so `config.py`'s existing `REPO_ROOT` derivation resolves to `/` unmodified. Not called out in plan.md, which only anticipated the model path moving.
- [ ] T009 [US1] Run `docker compose up --build`, confirm all three containers start with no errors, and confirm the client is reachable in a browser with the trail map/list loading (quickstart.md Scenario 1, first half) — **BLOCKED**: `docker compose config` validates cleanly and `client`'s image builds fine standalone (`npm run build` verified directly), but Docker Desktop's engine did not come up in this environment/session (`docker info` kept failing to reach `dockerDesktopLinuxEngine` after being launched and given several minutes) — needs the user to get Docker Desktop fully running (check for a stuck first-run prompt) before this can be executed
- [ ] T010 [US1] Verify persistence: `docker compose down` (no `-v`) then `docker compose up` again, confirm previously visible trail data is still present (quickstart.md Scenario 1 persistence check; validates FR-002/SC-005) — **BLOCKED** on the same Docker Desktop issue as T009

**Checkpoint**: User Story 1 is fully functional and independently testable — the stack runs and serves non-model-dependent data end-to-end.

---

## Phase 4: User Story 2 - Server loads the prediction model from S3 (Priority: P1)

**Goal**: The containerized server fetches `condition_models.joblib` from S3 (no local/mounted model file) and caches it in memory for the process lifetime.

**Independent Test**: With US1's stack running and valid S3 env vars/credentials set, call the conditions-prediction endpoint for a known trail/date and confirm it succeeds; confirm via server logs that exactly one S3 fetch occurs across multiple requests.

### Implementation for User Story 2

- [X] T011 [US2] Replace `CONDITION_MODELS_PATH` local-path constant in `server/app/config.py` with `MODEL_S3_BUCKET`/`MODEL_S3_KEY` env-var-backed config values (per [contracts/env-vars.md](./contracts/env-vars.md))
- [X] T012 [US2] Rewrite `_load_model_bundle()` in `server/app/services/conditions.py` to fetch the object via `boto3`'s `get_object`, `joblib.load` the body from an in-memory `io.BytesIO` buffer, and set `bundle["version"]` from the fetch response's `LastModified` timestamp instead of local file mtime — keep the existing module-level `_MODEL_BUNDLE` cache-once-per-process pattern unchanged (per [research.md](./research.md) §1–§2, [contracts/s3-model-object.md](./contracts/s3-model-object.md))
- [X] T013 [US2] Add clear, logged error handling in `_load_model_bundle()` for each failure mode in [contracts/s3-model-object.md](./contracts/s3-model-object.md) — missing object, unreachable/network error, invalid credentials, corrupted artifact (`joblib.load` failure) — per FR-009. Implemented as structured `HTTPException`s via the module's existing `_error()` helper (503 `model_unavailable` for config/fetch/network failures, 500 `model_corrupted` for a bad artifact) rather than a bare `RuntimeError`, matching how every other failure mode in this file is already surfaced to API callers.
- [X] T014 [P] [US2] Add unit tests in `server/tests/test_conditions.py` mocking `boto3` to cover: successful fetch populates the bundle and `version` from `LastModified`; a second call within the same process does not re-invoke the mocked S3 client (fetch-once caching, FR-005); each failure mode from T013 raises/logs the expected clear error. All 5 new tests pass (`pytest tests/test_conditions.py`: 18 passed); full suite: 30 passed, 9 skipped (pre-existing DB-dependent skips, unrelated to this feature).
- [ ] T015 [US2] Run quickstart.md Scenario 2 end-to-end against a real S3 bucket/object: confirm a conditions request succeeds with a `modelVersion` in the response, confirm no local model file exists in the built server image, confirm the caching and failure-mode checks — **BLOCKED**: needs a real S3 bucket with `condition_models.joblib` uploaded and real AWS credentials, which weren't available in this session; unit-level coverage (T014) exercises the same code paths against a mocked S3 client instead

**Checkpoint**: User Stories 1 and 2 both work independently and together — the full stack runs and conditions predictions are served from an S3-backed model.

---

## Phase 5: User Story 3 - Deploy the containerized app to a hosting environment (Priority: P2)

**Goal**: The same built images run against a different database and S3 model location purely through environment variable changes, with the `data/` training pipeline confirmed absent from the stack.

**Independent Test**: Point the existing images at a different `DATABASE_URL` and different `MODEL_S3_BUCKET`/`MODEL_S3_KEY` values with no source change; confirm the server connects to the new DB and serves predictions from the new model location.

### Implementation for User Story 3

- [X] T016 [US3] Replace the hardcoded `API_BASE` in `client/src/api/trails.ts` with `import.meta.env.VITE_API_BASE`, defaulting to `http://localhost:8000` when unset so non-Docker local dev is unaffected (per [research.md](./research.md) §4). Verified `vite/client` types already give `import.meta.env` a fallback index signature, so no new `.d.ts` was needed; `npm run build` (`tsc -b && vite build`) succeeds.
- [X] T017 [US3] Wire `VITE_API_BASE` as a build arg through `client/Dockerfile` (`ARG`/`ENV` before `npm run build`) and `docker-compose.yml`'s `client.build.args` (per [contracts/env-vars.md](./contracts/env-vars.md); note this is a build-time value — changing it for a new environment requires rebuilding the client image, unlike the server's runtime env vars)
- [ ] T018 [US3] Run quickstart.md Scenario 3: start the images against a different `DATABASE_URL` and different `MODEL_S3_BUCKET`/`MODEL_S3_KEY` via `.env` changes alone, confirm the server connects to the new DB and serves predictions from the new model location without a rebuild (validates SC-003/FR-011 for the server's runtime config) — **BLOCKED** on the same Docker Desktop engine + real S3 access issues as T009/T015
- [ ] T019 [US3] Confirm `docker compose ps` lists only `db`, `server`, `client` — no container corresponds to the `data/` training pipeline (validates FR-008) — **BLOCKED** on Docker Desktop engine as above (though this is true by construction: `docker-compose.yml` only defines these three services)

**Checkpoint**: All three user stories are independently functional; the images are portable across environments via configuration alone (except the client's build-time API base, a documented exception).

---

## Phase 6: Polish & Cross-Cutting Concerns

**Purpose**: Documentation and final end-to-end validation across all stories.

- [X] T020 [P] Document the `docker compose up` workflow and required `.env` variables in `server/README.md`
- [X] T021 [P] Add a top-level note (e.g. in the repo root README, creating one if none exists) pointing to `.env.example` and `specs/007-docker-containerization/quickstart.md` for the Docker workflow. No root README existed; created one.
- [ ] T022 Run the full [quickstart.md](./quickstart.md) validation end-to-end (all three scenarios plus the FR-010 config-validation check with a missing required variable) and confirm every check passes — **BLOCKED**: depends on T009/T010/T015/T018/T019 above, all pending a working Docker Desktop engine and real S3 access

---

## Dependencies & Execution Order

### Phase Dependencies

- **Setup (Phase 1)**: No dependencies — start immediately.
- **Foundational (Phase 2)**: Depends on Setup (T003's `boto3` addition and T001/T002's `.dockerignore` files are referenced by the Dockerfiles) — BLOCKS all user stories.
- **User Stories (Phase 3-5)**: All depend on Foundational completion.
  - US1 (P1) has no dependency on US2/US3.
  - US2 (P1) is code-level and independent of US1's compose file, but its quickstart verification (T015) runs against the stack US1 stands up — sequence US1 before verifying US2 in practice, even though the code changes themselves (T011-T014) don't depend on US1's tasks.
  - US3 (P2) depends on US1's `docker-compose.yml` (T008) existing to add build args to it (T017) and to run its verification (T018/T019).
- **Polish (Phase 6)**: Depends on all three user stories being complete.

### Parallel Opportunities

- T001, T002, T003 (Setup) can all run in parallel — different files.
- T005, T006 (Foundational Dockerfiles) can run in parallel — different files/services.
- T014 (US2 unit tests) can run in parallel with T015 (US2 manual quickstart verification) once T011-T013 are done.
- T020, T021 (Polish docs) can run in parallel.

---

## Parallel Example: Setup + Foundational

```bash
# Setup phase, launch together:
Task: "Create server/.dockerignore"
Task: "Create client/.dockerignore"
Task: "Add boto3 to server/requirements.txt"

# Foundational phase, launch together:
Task: "Create server/Dockerfile"
Task: "Create client/Dockerfile"
```

---

## Implementation Strategy

### MVP First (User Story 1 Only)

1. Complete Phase 1 (Setup) and Phase 2 (Foundational).
2. Complete Phase 3 (US1): one-command local stack with DB + server + client.
3. **STOP and VALIDATE**: run quickstart.md Scenario 1 independently — this is a usable MVP even before the model moves to S3 (non-model endpoints work end-to-end).

### Incremental Delivery

1. Setup + Foundational → images build, CORS is configurable.
2. Add US1 → full stack runs locally → demo-able MVP.
3. Add US2 → conditions predictions now come from S3, not a local file → demo-able.
4. Add US3 → same images verified portable to a second environment → deployment-ready.
5. Polish → documented and fully quickstart-validated.
