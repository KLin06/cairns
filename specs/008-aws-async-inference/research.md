# Phase 0 Research: Async Serverless Model Inference at Scale

The bulk of this feature's research and design reasoning already lives in [aws/SYSTEM_DESIGN.md](../../aws/SYSTEM_DESIGN.md) — written in the requirements → capacity-estimation → architecture → component-deep-dive → bottlenecks structure of a systems-design-interview answer, at the user's explicit request. This file summarizes the decisions in the Decision/Rationale/Alternatives format the plan workflow expects, and points to the fuller writeup rather than duplicating it. A plain-language version of the same argument is in [aws/DESIGN_JUSTIFICATION.md](../../aws/DESIGN_JUSTIFICATION.md).

## 1. Compute: Lambda (container image) vs. a fixed EC2/ECS worker pool

**Decision**: AWS Lambda, packaged as a container image, triggered by SQS.

**Rationale**: The workload is bursty and mostly idle (one nightly-batch-shaped spike, not continuous traffic) — Lambda's per-invocation billing and SQS-driven auto-scaling match that shape without hand-written autoscaling policies. A container image (not zip/layers) is required because the reused prediction code pulls in scikit-learn/pandas/joblib, well past the 250MB zip limit.

**Alternatives considered**: A fixed EC2/ECS worker pool — rejected because it has to be sized for a peak that only occurs briefly and rarely, wasting capacity the rest of the time. See `aws/SYSTEM_DESIGN.md` §6.2 and §3.

## 2. Storage for computed predictions: DynamoDB vs. writing into Postgres

**Decision**: DynamoDB, on-demand billing, partition key `trailId` + sort key `date`.

**Rationale**: The access pattern is pure point lookup by key — no joins or relational structure needed. More importantly, keeping the results store separate from Postgres means a burst of writes can never contend with reads for an already-computed prediction, which is what SC-005 (flat, fast read latency regardless of write load) requires structurally rather than by tuning.

**Alternatives considered**: Writing predictions into the existing Postgres — rejected for the read/write contention reason above. See `aws/SYSTEM_DESIGN.md` §6.3.

## 3. Database for trail data: provision one vs. assume one exists

**Decision**: Provision a database as part of this feature's own infrastructure-as-code, in a private VPC. Originally Aurora Serverless v2 (Postgres-compatible); switched to a plain single-instance RDS Postgres (`db.t3.micro`) after a real `cdk deploy` attempt against the target AWS account failed at `AWS::RDS::DBCluster` with an account-plan restriction on Aurora specifically (`"...free plan accounts you need to set WithExpressConfiguration..."` — no corresponding property exists anywhere in `aws-cdk-lib`, so this isn't fixable in this stack's code).

**Rationale**: The Lambda runs in AWS and has no network path to spec 007's local docker-compose Postgres — that's not a networking detail to assume away, the pipeline cannot function without a reachable database (FR-015). Aurora Serverless v2 was the initial choice specifically to keep the same "pay for what you use" reasoning as the rest of the design (`serverlessV2AutoPauseDuration` scales capacity down when idle). Once that was blocked by the account restriction, `db.t3.micro` was chosen as the fallback because it's RDS-Free-Tier-eligible (Aurora isn't) and, at this workload's small scale, cheaper in raw dollars than Aurora Serverless v2's ACU pricing floor would have been anyway — the underlying "match cost to actual usage" goal is preserved, just through a different, less elegant mechanism (a cheap fixed instance rather than one that scales down further).

**Alternatives considered**: Aurora Serverless v2 (originally chosen, blocked by account restriction — revisit if this ever runs on an account without that restriction); assuming an externally-reachable database already exists (rejected outright — this was an earlier draft's oversight, corrected once surfaced; see spec.md FR-015/FR-016 and Assumptions). See `aws/SYSTEM_DESIGN.md` §6.5.

## 4. Networking for the database: public-with-security-group vs. private VPC

**Decision**: Private VPC — a three-tier layout (public/NAT, private-with-egress/Lambda, private-isolated/database), with a security-group rule as a second access-control layer beyond the credential itself (FR-016).

**Rationale**: A password-only, publicly-reachable database is one leaked credential away from being fully open. Private networking makes network position itself a required condition for access, not just an added inconvenience for legitimate traffic (the Lambda already needs to run somewhere, so putting it in the same VPC costs no extra step). The NAT Gateway is a consequence of this choice (the Lambda needs internet egress for Open-Meteo, which isn't reachable via any VPC endpoint), not something wanted for its own sake — S3/DynamoDB traffic bypasses it via free Gateway Endpoints.

**Alternatives considered**: Public RDS/Aurora endpoint gated only by credentials (rejected — see above). See `aws/SYSTEM_DESIGN.md` §6.5.

## 5. Trail description data source for the Lambda: S3 mirror vs. Postgres migration

**Decision (superseding an earlier draft)**: Migrate the synchronous server's own `_load_description()`/`_get_trail_location()` to read the `trails` table (via `server/db/migrations/0004_add_model_terrain_features.sql`), rather than mirroring `enriched_descriptions/` JSON files into S3 for the Lambda to fetch-and-cache.

**Rationale**: An earlier version of this design solved "the Lambda has no filesystem to read `enriched_descriptions/{trailId}.json` from" by syncing those files to S3 and caching them in `/tmp` per trail — workable, but it required a second data-sync step to keep in sync with the pipeline, and left the synchronous and asynchronous paths reading trail data through two different mechanisms. Since the Lambda already needs a Postgres connection for activity data, migrating description reads onto that same connection eliminates the S3-mirror/cache machinery entirely and unifies both paths onto one code path — a strictly better outcome once surfaced, not just a lateral tradeoff.

**Alternatives considered**: The S3-mirror-and-cache approach (originally chosen, since discarded); baking `enriched_descriptions/` into the Lambda's container image at build time (rejected — couples redeploying the Lambda to every enrichment-pipeline run). See `aws/SYSTEM_DESIGN.md` §6.2 for the full before/after, and `data-model.md` (this directory) for the schema change itself.

## 6. Dead-letter handling: bounded SQS redrive vs. custom permanent/transient routing

**Decision**: A standard SQS redrive policy (`maxReceiveCount: 5`) to a dead-letter queue, with no custom logic distinguishing a permanently-invalid request (will never succeed) from a transient one (might succeed on retry).

**Rationale**: Both failure classes get reported as an SQS batch item failure and retried up to the same bound before landing in the DLQ. A more precise design would route permanent failures (e.g. a validation error) directly to the DLQ, skipping wasted retries — deliberately not built, since it requires manually bypassing SQS's own redrive accounting for a workload where the wasted retries cost a handful of extra Lambda invocations, not meaningful time or money at the scale estimated in §3.

**Alternatives considered**: Immediate custom DLQ routing for known-permanent failures — left as documented future work. See `aws/SYSTEM_DESIGN.md` §6.4 and §10.

## 7. Lambda Docker build context: repo root, and what that requires

**Decision**: The Lambda's container image build context is the repository root (not `aws/lambda/`), with an explicit root-level `.dockerignore` scoping it down to what the image actually needs.

**Rationale**: The Dockerfile needs `COPY server/app` and `COPY server/db` to reuse the existing prediction code unmodified (FR-003) — that requires the build context to include `server/`, which means the context has to be the repo root (CDK's `fromImageAsset` supports a context directory + a `file` pointing at a Dockerfile elsewhere within it). Discovered the hard way: without a root `.dockerignore`, CDK's asset-staging step hashed and copied the *entire* repository — `client/node_modules`, `server/venv`, `aws/cdk`'s own `node_modules`, `.git`, a 400MB+ file under `data/` — before `docker build` ever ran, consuming 2.4GB+ of memory and 30+ minutes with zero CloudFormation activity to show for it, during a real `cdk deploy` attempt. `cdk synth --no-staging` (used earlier to validate the stack's structure) never exercises this path, so it didn't catch the problem.

**Alternatives considered**: Restructure so the Lambda's own code doesn't need files outside `aws/lambda/` (would mean duplicating `server/app`/`server/db` instead of reusing them — rejected, directly conflicts with FR-003/constitution Principle II). See `aws/SYSTEM_DESIGN.md` §6.2.

## 8. Lambda base image: Python 3.11 (Amazon Linux 2) vs. Python 3.12 (Amazon Linux 2023)

**Decision**: `public.ecr.aws/lambda/python:3.12`, not `:3.11`.

**Rationale**: `:3.11` is built on Amazon Linux 2, whose default `gcc` (7.3.1) is too old to build `numpy` from source (`numpy` requires gcc≥9.3) and whose glibc is too old to match `numpy`'s prebuilt wheel tags for the version pip resolved — pip fell back to a source build that then failed outright. `:3.12` is built on Amazon Linux 2023 (modern gcc and glibc), so the same `pip install` resolves prebuilt wheels for every dependency with no compiler needed at all. Discovered via a real `docker build` of the Lambda image, not `cdk synth`.

**Alternatives considered**: Installing a newer gcc devtoolset on top of Amazon Linux 2 (viable, but more moving parts and slower builds than just using a base image with a modern toolchain already); pinning `numpy`/`pandas` to older versions with broader wheel coverage (would still leave AL2's old toolchain as a standing risk for any other future compiled dependency). See `aws/SYSTEM_DESIGN.md` §6.2.
