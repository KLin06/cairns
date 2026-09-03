# Implementation Plan: Async Serverless Model Inference at Scale (SQS + Lambda + DynamoDB)

**Branch**: `008-aws-async-inference` | **Date**: 2026-08-30 | **Spec**: [spec.md](./spec.md)

**Input**: Feature specification from `/specs/008-aws-async-inference/spec.md`

**Note**: This plan documents a system that was already substantially built and verified during the conversation that produced it, rather than being written purely ahead of implementation — the design decisions below reflect what's actually running in `aws/`, not a hypothetical. It exists so this feature has the same plan/research/data-model/contracts/quickstart structure as spec 007, for consistency and future reference.

**Revision note (post real-deploy-attempt)**: the database was originally Aurora Serverless v2; a real `cdk deploy` attempt against the target AWS account failed with `AWS::RDS::DBCluster CREATE_FAILED: "To use Aurora clusters with free plan accounts you need to set WithExpressConfiguration..."` — an account-level restriction with no corresponding property anywhere in `aws-cdk-lib`, not something fixable in this stack's code. Switched to a plain single-instance RDS Postgres (`db.t3.micro`) instead, which is both RDS-Free-Tier-eligible (Aurora isn't) and cheaper in raw dollars at this workload's tiny scale than Aurora Serverless v2's ACU pricing floor. Two more real bugs were found and fixed during the same deploy attempts: (1) the Lambda's Docker build context had no root-level `.dockerignore`, so CDK's asset staging was hashing/copying the *entire* repo (client's `node_modules`, server's `venv`, `aws/cdk`'s own `node_modules`, `.git`, a 400MB+ file under `data/`) before ever invoking `docker build` — a 30+ minute hang with zero CloudFormation activity; (2) the Lambda's base image (`public.ecr.aws/lambda/python:3.11`, Amazon Linux 2) has a gcc too old (7.3.1) to build `numpy` from source and a glibc too old to use prebuilt `numpy` wheels — switched the base image to `public.ecr.aws/lambda/python:3.12` (Amazon Linux 2023) instead of hand-installing a newer devtoolset. All three fixes are reflected below and in `aws/`.

## Summary

An SQS → Lambda → DynamoDB pipeline that computes trail-conditions predictions asynchronously and at scale, deployed via AWS CDK (`aws/cdk/`), alongside — not replacing — the existing synchronous `/conditions` endpoint. The Lambda reuses `server/app`/`server/db` unmodified as a container image. Because the compute layer runs in AWS and has no path to the developer's local Postgres, this feature also provisions its own RDS Postgres instance (in a private VPC) and, as a follow-on migration, moved the synchronous server's own trail-description reads off local flat files and onto that same database shape (`server/db/migrations/0004`), so both the sync and async paths now read trail data through one identical code path.

## Technical Context

**Language/Version**: Python 3.12 (Lambda handler + reused `server/` code — bumped from 3.11 during deployment, see Revision note above); TypeScript 5.4 / Node 20+ (CDK app, `aws-cdk-lib` 2.267.0)

**Primary Dependencies**: `aws-cdk-lib` v2, `constructs` (CDK app); `boto3`, FastAPI, scikit-learn, pandas, joblib, psycopg2 (reused from `server/requirements.txt`, spec 007); AWS services used: SQS, Lambda (container image via ECR), DynamoDB, RDS for PostgreSQL (`db.t3.micro`, single instance), Secrets Manager, SNS, CloudWatch, EC2/VPC (NAT Gateway, S3/DynamoDB Gateway Endpoints)

**Storage**: DynamoDB (`cairns-trail-conditions-predictions`, computed results — new); RDS Postgres (trail records + activity, provisioned by this feature, VPC-isolated, `db.t3.micro`); S3 (model artifact only, existing bucket from spec 007 — no longer holds trail descriptions, see Data Model)

**Testing**: No new automated test suite for the CDK stack/Lambda itself — validated via `cdk synth` (confirmed VPC/RDS/security-group/IAM resources synthesize correctly), a direct `docker build` of the Lambda image (confirmed it completes cleanly post-fix), and a real `cdk deploy` attempt against the target AWS account (which is what surfaced the three bugs in the Revision note above). The server-side migration this feature required (`conditions.py`/`weather.py`/`backfill.py`) IS covered by the existing pytest suite (`server/tests/test_conditions.py`, `test_weather.py`, `test_backfill.py`) — re-verified end-to-end against a real (throwaway, Dockerized) Postgres instance: 38/38 passed.

**Target Platform**: AWS (operator-chosen account/region), Lambda container-image runtime inside a private VPC subnet

**Project Type**: Additive serverless infrastructure (`aws/`) alongside the existing web app (spec 007's Option 2 structure, untouched), plus a small, targeted data-access migration inside `server/` (three files, one new migration)

**Performance Goals**: SC-001 (≥1,000-request burst drained within minutes), SC-005 (sub-second DynamoDB reads regardless of concurrent write load)

**Constraints**: FR-004 (compute auto-scales with backlog, no manual intervention), FR-013 (queue/compute/storage independently scalable), FR-014/FR-016 (secrets never in plaintext; database not reachable on a password alone — private networking required), FR-010 (the synchronous endpoint's external behavior/contract must not change)

**Scale/Scope**: ~2,000 trails × 16-day forecast horizon ≈ 32,000 requests for a full nightly refresh (illustrative estimate, `aws/SYSTEM_DESIGN.md` §3) — bursty/intermittent, not continuous high-throughput

## Constitution Check

*GATE: Must pass before Phase 0 research. Re-check after Phase 1 design.*

- **Principle II (Feature Parity Between Training and Inference)** — PASS, strengthened. The async path calls `conditions.py`'s prediction logic directly and unmodified (FR-003). The follow-on database migration (moving `_load_description`/`_get_trail_location` off local files) means both the synchronous and asynchronous paths now read trail data through the *same* Postgres-backed code, closing a potential drift surface rather than opening one.
- **Principle VIII (Honest Uncertainty in Predictions)** — PASS. The `confidence` field's data source (`trail_activity` table) is unchanged by this feature; the async path returns the identical `ConditionsResponse` shape, confidence included.
- **Principle IX (Selective Field Storage)** — PASS. The new `trails` columns added by migration 0004 (`soil_drainage_rank`, `soil_texture_mud_potential`, `soil_texture_group`) are exactly the three fields the live inference path needs and didn't already have — not a wholesale dump of `enriched_descriptions`' JSON.
- **Principle X (Scoped JSONB Usage)** — PASS. Those same three new columns are fixed-shape scalars (two integers, one short text label) stored as real typed columns, not JSONB — consistent with the principle's own reasoning, not an exception to it.
- **Principle I (Endpoint Separation)** — Not implicated; this feature adds a new pipeline, not a new endpoint, and FR-010 explicitly requires the existing endpoint's behavior stay unchanged.

**Result: PASS. No violations to justify; Complexity Tracking is not needed.**

## Project Structure

### Documentation (this feature)

```text
specs/008-aws-async-inference/
├── plan.md              # This file
├── research.md          # Phase 0 output - summarizes decisions, points to aws/SYSTEM_DESIGN.md for full depth
├── data-model.md         # Phase 1 output
├── quickstart.md        # Phase 1 output - points to aws/README.md for the actual runnable steps
├── contracts/           # Phase 1 output
│   ├── sqs-message.md
│   ├── dynamodb-item.md
│   ├── env-vars.md
│   └── trails-schema-addition.md
└── tasks.md             # Not generated for this feature - see note below
```

**Note on tasks.md**: unlike spec 007, this feature's implementation happened conversationally (design → build → verify, iterating in response to follow-up questions) rather than from a pre-generated task list, and is already complete and verified as of this plan being written. `/speckit-tasks` is not being run retroactively for work that's done; this plan/research/data-model/contracts/quickstart set exists for documentation parity with spec 007, not to drive not-yet-started work.

### Source Code (repository root)

```text
aws/                                  # NEW (all of it)
├── SYSTEM_DESIGN.md                  # Full requirements/estimation/architecture/deep-dive/bottlenecks writeup
├── DESIGN_JUSTIFICATION.md           # Plain-language version of the same argument
├── README.md                         # Deploy/populate-database/try-it/tear-down walkthrough
├── cdk/
│   ├── bin/aws.ts                    # CDK app entry (modelBucketName + alertEmail context only)
│   └── lib/inference-stack.ts        # VPC, RDS Postgres (db.t3.micro), SQS+DLQ, DynamoDB, Lambda, SNS, CloudWatch alarms
└── lambda/
    ├── Dockerfile                    # COPYs server/app + server/db unmodified
    └── handler.py                    # SQS batch handler; builds DATABASE_URL from the RDS instance's generated secret + plain env vars

server/                                # MODIFIED (targeted, per the Postgres migration)
├── db/migrations/0004_add_model_terrain_features.sql   # NEW
├── db/backfill.py                    # MODIFIED - 3 new TRAIL_COLUMNS + upsert SQL
├── app/services/trail_info.py        # MODIFIED - derive_trail_record() extracts 3 new fields
├── app/services/conditions.py        # MODIFIED - _load_description() reads trails table, not a file
├── app/services/weather.py           # MODIFIED - _get_trail_location() reads trails table, not a file
└── tests/
    ├── conftest.py                   # MODIFIED - applies all migrations (0001-0004), not just 0001 (pre-existing gap, fixed)
    ├── test_conditions.py            # MODIFIED - enriched_trail fixture inserts a DB row instead of writing a file
    └── test_weather.py               # MODIFIED - same fixture change
```

**Structure Decision**: `aws/` is entirely new and self-contained (infra + its own docs), matching the user's explicit request to keep it in one place. The `server/` changes are a small, targeted migration (5 files + 1 new migration) rather than a restructuring — `client/` and the rest of `server/` are untouched.

## Complexity Tracking

*Not applicable — Constitution Check passed with no violations.*
