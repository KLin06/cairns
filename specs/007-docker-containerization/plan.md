# Implementation Plan: Docker Containerization with S3-Backed Model Loading

**Branch**: `007-docker-containerization` | **Date**: 2026-08-29 | **Spec**: [spec.md](./spec.md)

**Input**: Feature specification from `/specs/007-docker-containerization/spec.md`

## Summary

Package the existing three-part app (Postgres, FastAPI server, Vite/React client) into Docker images orchestrated by a single `docker-compose.yml` for local development, and change the server's model-loading path (`server/app/services/conditions.py::_load_model_bundle`) so it fetches `condition_models.joblib` from S3 via `boto3` and caches it locally in the running process, instead of reading it directly off `server/app/config.py::CONDITION_MODELS_PATH`. The `data/` training pipeline is explicitly excluded from the compose stack. All environment-specific values (DB connection, S3 location/credentials, client API base URL) move to environment variables so the same images run unmodified in a different environment.

## Technical Context

**Language/Version**: Python 3.11+ (server, matches existing `server/venv`), Node 20+ / TypeScript (client), SQL (PostgreSQL 16)

**Primary Dependencies**: FastAPI, uvicorn, psycopg2-binary, joblib, scikit-learn (existing, `server/requirements.txt`); `boto3` (new, for S3 fetch); React 19, Vite (existing, `client/package.json`); Docker Engine + Docker Compose (new, infra-only)

**Storage**: PostgreSQL (containerized, unchanged schema under `server/db/migrations`); S3 (new — read-only from the app's perspective, holds `condition_models.joblib`)

**Testing**: pytest (existing `server/tests/`, unchanged); this feature adds no new automated test framework — its own verification is the `quickstart.md` manual/scripted validation of the compose stack, plus one new unit-level test for the S3-backed model loader (mocking `boto3`)

**Target Platform**: Linux containers via Docker Compose for local dev; the same images are runnable on any Docker-compatible host (no specific orchestrator/cloud target chosen yet, per spec Assumptions)

**Project Type**: Web application (frontend + backend), containerized — Option 2 structure (existing `client/` + `server/` split), plus new infra config (`docker-compose.yml`, `Dockerfile`s) and one `data/` exclusion

**Performance Goals**: N/A beyond preserving current behavior — containerization must not add per-request latency; the one caching requirement (FR-005) is that S3 is hit at most once per server process lifetime, not once per request

**Constraints**: No source/image rebuild required to point at a different DB or S3 location (FR-011); server must fail fast on missing config or an unfetchable/invalid model (FR-009, FR-010); `data/` pipeline must not be started, scheduled, or health-checked by the stack (FR-008)

**Scale/Scope**: One `docker-compose.yml` with 3 services (`db`, `server`, `client`) + 1 named volume; 2 new Dockerfiles; one code change to `conditions.py`/`config.py` for S3 fetching; one code change to `client/src/api/trails.ts` to make `API_BASE` env-configurable at build time

## Constitution Check

*GATE: Must pass before Phase 0 research. Re-check after Phase 1 design.*

This feature is infrastructure/deployment work — it does not touch prediction logic, UI structure, or data derivation, so most of the ten principles are not implicated. The two that are relevant both **PASS**:

- **Principle II (Feature Parity Between Training and Inference)** — PASS. The model bundle's *content* and the feature-flattening logic in `conditions.py` are unchanged; only the bundle's *retrieval location* changes (S3 instead of local disk). Training-table generation (`build_training_table.py`) is untouched. No risk of train/inference drift is introduced.
- **Principle VIII (Honest Uncertainty in Predictions)** — PASS, with one design consequence: `_load_model_bundle`'s existing `version` field (derived today from `os.path.getmtime(CONDITION_MODELS_PATH)`) cannot keep using local-file mtime once the file is downloaded fresh into a cache on every container start — that would report today's date as the model version regardless of when it was actually trained, silently misrepresenting model provenance. Phase 0 research resolves this (S3 object's `LastModified` becomes the version source instead of local mtime).

No other principle (I, III, IV, V, VI, VII, IX, X) governs deployment topology, container packaging, or credential plumbing — they concern endpoint semantics, UI behavior, and DB schema shape, none of which this feature changes.

**Result: PASS. No violations to justify; Complexity Tracking section is not needed.**

## Project Structure

### Documentation (this feature)

```text
specs/007-docker-containerization/
├── plan.md              # This file
├── research.md          # Phase 0 output
├── data-model.md         # Phase 1 output
├── quickstart.md        # Phase 1 output
├── contracts/           # Phase 1 output
│   ├── env-vars.md
│   └── s3-model-object.md
└── tasks.md             # Phase 2 output (/speckit-tasks - not created here)
```

### Source Code (repository root)

```text
server/
├── Dockerfile                       # NEW - Python base image, installs requirements.txt, runs uvicorn
├── .dockerignore                    # NEW
├── app/
│   ├── config.py                    # MODIFIED - S3 bucket/key/cache-path env vars alongside existing paths
│   └── services/
│       └── conditions.py            # MODIFIED - _load_model_bundle fetches from S3 + local cache, version from S3 metadata
├── requirements.txt                 # MODIFIED - add boto3
└── tests/
    └── test_conditions.py           # MODIFIED - add S3 fetch/cache unit tests (mocked boto3)

client/
├── Dockerfile                       # NEW - multi-stage: node build -> static file server
├── .dockerignore                    # NEW
└── src/api/trails.ts                # MODIFIED - API_BASE from build-time env var instead of hardcoded

docker-compose.yml                   # NEW - db + server + client services, one named volume
.env.example                         # NEW - documents all required/optional env vars (no real secrets)
```

**Structure Decision**: Existing `client/` + `server/` split (Option 2: web application) is preserved as-is; this feature is additive at the repo root (`docker-compose.yml`, `.env.example`) and per-service (`server/Dockerfile`, `client/Dockerfile`) rather than a restructuring. `data/` receives no Docker artifacts — it stays a manually-run Python project outside the compose stack, matching FR-008.

## Complexity Tracking

*Not applicable — Constitution Check passed with no violations.*
