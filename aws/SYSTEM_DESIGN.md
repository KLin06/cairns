# System Design: Async Serverless Trail-Conditions Inference

Companion design doc to [specs/008-aws-async-inference/spec.md](../specs/008-aws-async-inference/spec.md). Written in the requirements → estimation → high-level design → deep dive → bottlenecks structure of a systems-design-interview answer (e.g. the web crawler chapter of *Grokking the System Design Interview*), because the shape of the problem is genuinely similar: a producer enqueues units of work, a fleet of stateless workers pulls from the queue and does I/O-heavy processing per unit, results land in a store keyed for fast point lookups, and the whole thing has to keep working when a dependency misbehaves.

## 1. Problem Statement

The existing FastAPI server ([specs/007-docker-containerization](../specs/007-docker-containerization/spec.md)) computes a trail-conditions prediction synchronously, in-process, once per HTTP request. That's the right design for a single user checking one trail on the website — low latency, simple. It is the *wrong* design for bulk demand: precomputing predictions for every trail across a 16-day forecast horizon, or absorbing a burst of requests (e.g. a scheduled nightly refresh, or a spike from many users at once) without scaling the always-on web server itself.

This system adds a second, asynchronous path for exactly that bulk/bursty case: submit a request, let a fleet of workers that scale with backlog size process it, and read the result back out later. It does not replace the synchronous endpoint.

## 2. Requirements

**Functional** (see spec.md for the full, authoritative list):
- Accept a prediction request (trail ID + date) without blocking the submitter.
- Compute the same prediction the synchronous endpoint would, using the same model and feature logic.
- Persist the result, keyed for retrieval by trail ID + date, overwriting any prior result for that key.
- Route unprocessable requests to a dead-letter location with enough context to diagnose them, and alert an operator when that starts happening.

**Non-functional** (this is where a systems-design answer earns its keep):
- **Scalability**: must absorb a burst orders of magnitude above steady-state without manual intervention (SC-001).
- **Durability**: a request that's been accepted must never silently vanish (SC-003).
- **Read latency**: retrieving an already-computed prediction must be fast and *flat* regardless of how much write load the system is concurrently absorbing (SC-005) — this rules out a design where reads and the bulk compute path share a bottleneck.
- **Operability**: failures must surface as alerts, not require polling (SC-007).
- **Reproducibility**: the whole thing is defined as code (CDK), not console clicks (FR-011/SC-006).

## 3. Capacity Estimation (back-of-envelope)

Concrete numbers aren't available for this app's real trail count, so — in the spirit of a systems-design interview, where the point is to reason from stated assumptions, not to know the real figure — assume:

- **~2,000 trails** in the catalog (a regional trail-conditions app, not a global one).
- **16-day forecast horizon** per trail (Open-Meteo's limit, per constitution Principle III).
- A nightly batch job that refreshes predictions for every trail across the full horizon: `2,000 × 16 = 32,000` requests per run.

That's the burst this system needs to absorb, not the steady-state rate:

- If drained in, say, 5 minutes: `32,000 / 300s ≈ 107 requests/sec` sustained for that window — trivial for SQS (which handles orders of magnitude more) and easily covered by Lambda's default per-account concurrency (1,000 concurrent executions unless raised), even before requesting a limit increase.
- **Storage**: one item per (trail, date) pair. At steady state, roughly `2,000 trails × 16 days ≈ 32,000 live items` (older dates roll off / get overwritten as the horizon moves forward). Each item is small — a handful of per-condition probabilities plus metadata, well under 1KB — so total table size stays in the low tens of MB. This is nowhere near DynamoDB's partitioning concerns; the design doesn't need to think hard about hot-partition risk at this scale (see §9 for what would change if this were 1000x bigger).
- **DLQ volume**: expected to be ~0 in steady state; sized for "a dependency had a bad five minutes," not sustained load.

The headline takeaway: this system is *not* big-data scale. The reason to use SQS/Lambda/DynamoDB here isn't raw throughput — it's that the workload is bursty and intermittent (a nightly job, not continuous traffic), and serverless means paying per-invocation instead of running idle compute between bursts.

## 4. High-Level Design

```
                    ┌─────────────────────┐
  producer  ──────▶ │   SQS request queue   │
 (batch job,        │  (cairns-prediction-  │
  or any caller)    │      requests)        │
                    └──────────┬────────────┘
                               │ triggers, auto-scales with backlog
                               ▼
                    ┌─────────────────────┐        ┌──────────────┐
                    │   Lambda worker      │──────▶ │ S3: model    │
                    │ (container image,    │        │ (spec 007)   │
                    │  reuses server/app)  │◀───────┤              │
                    └──────────┬────────────┘        └──────────────┘
                               │                       ┌──────────────┐
                               │◀──────────────────────┤ Postgres     │
                               │  (trail activity +    │ (this stack, │
                               │   trail descriptions)  │  VPC-isolated)│
                               │                       └──────────────┘
                               │                       ┌──────────────┐
                               │◀──────────────────────┤ Open-Meteo   │
                               │   (weather forecast)   │ (external)   │
                               ▼                       └──────────────┘
                    ┌─────────────────────┐
                    │  DynamoDB table       │──────▶ read by any later consumer
                    │  (trailId, date) →    │        (point lookup, no compute
                    │  stored prediction    │         path shared with writes)
                    └─────────────────────┘

        (message fails maxReceiveCount times)
                               │
                               ▼
                    ┌─────────────────────┐        ┌──────────────┐
                    │   SQS dead-letter    │──────▶ │ CloudWatch    │──▶ SNS ──▶ operator
                    │        queue          │        │ alarm on depth│         email
                    └─────────────────────┘        └──────────────┘
```

Key property this diagram is meant to make obvious: **the read path (DynamoDB `GetItem`) never touches the queue, the Lambda fleet, Postgres, or Open-Meteo.** Whatever load the write side is under, reads stay fast — this is what makes SC-005 achievable "for free" from the architecture rather than something to optimize later.

## 5. Message & Item Contracts

**SQS message body** (JSON):
```json
{ "trailId": "99887766", "date": "2026-09-15" }
```
Deliberately the same two fields the synchronous `/trails/{trail_id}/conditions` endpoint already accepts (FR-001) — a producer can build this message from the exact same inputs a UI would send to the synchronous endpoint.

**DynamoDB item** (`cairns-trail-conditions-predictions` table):
```json
{
  "trailId": "99887766",
  "date": "2026-09-15",
  "conditions": { "bugs": { "probability": 0.12, "predicted": false }, "...": "..." },
  "modelVersion": "2026-08-30",
  "confidence": { "reviewCount": 412, "limitedData": false },
  "computedAt": "2026-08-30T14:03:11Z"
}
```
Partition key `trailId`, sort key `date` — this is literally `ConditionsResponse` (`server/app/schemas.py`) plus one bookkeeping field (`computedAt`), not a new shape invented for this pipeline. A nice side effect of `date` as the sort key: `Query` for a single `trailId` with no filter returns every stored date for that trail in sorted order, for free, if a future feature ever wants "show the whole window for this trail" without 16 separate `GetItem` calls.

## 6. Component Deep Dive

### 6.1 SQS: standard queue, not FIFO

A **standard** queue was chosen over FIFO. FIFO buys strict ordering and exactly-once delivery, at a throughput ceiling (3,000 msg/sec with batching) and added latency. Neither ordering nor exactly-once matters here: two predictions for the same key computed in either order, or a message delivered twice, both resolve correctly because of how idempotency is handled below (§6.3) — so standard's higher throughput ceiling and simplicity win with no real tradeoff for this workload.

**Visibility timeout** is set to 180s — comfortably above the Lambda's own 90s timeout plus margin, so a message isn't returned to the queue (and double-processed by a second worker) while the first worker is still legitimately working on it, which is the single most common SQS misconfiguration.

### 6.2 Lambda: container image, not a zip/layers deployment

The prediction logic pulls in scikit-learn, pandas, and joblib (already true for the existing server) — well past the 250MB unzipped limit for a plain zip-based Lambda deployment package, and awkward to split across the 5-layer limit. A **container image** (up to 10GB) sidesteps the size ceiling entirely, and — more importantly for maintainability — lets this Lambda literally reuse `server/app` and `server/db` unmodified (see `aws/lambda/Dockerfile`) instead of maintaining a second copy of the prediction code. That directly satisfies constitution Principle II and spec 008's FR-003: this pipeline is a second *trigger*, not a second *implementation*.

**Two real deployment bugs this surfaced, worth recording rather than quietly fixing.** First: because the Dockerfile needs to `COPY server/app`/`server/db`, its build context is the *repo root*, not `aws/lambda/`. Without a root-level `.dockerignore`, CDK's asset-staging step hashed and copied the *entire* repository — `client/node_modules`, `server/venv`, `aws/cdk`'s own `node_modules`, `.git`, a 400MB+ file under `data/` — before `docker build` ever ran, silently consuming 2.4GB+ of memory and 30+ minutes with zero CloudFormation activity to show for it. The fix is a `.dockerignore` at the repo root (not just per-service ones), scoped to exactly what the Lambda image actually needs. Second: the Lambda base image (`public.ecr.aws/lambda/python:3.11`) is Amazon Linux 2, whose default `gcc` (7.3.1) is too old to build `numpy` from source and whose glibc is too old to match `numpy`'s prebuilt wheel tags — switching to the `python:3.12` tag (Amazon Linux 2023, modern toolchain) resolved it without hand-installing a devtoolset. Neither of these would show up in `cdk synth` with `--no-staging` (what was used to validate the stack's structure before ever attempting a real deploy) — only an actual `docker build`/`cdk deploy` exercises the asset-bundling path where they lived.

**Concurrency & scaling**: SQS-triggered Lambda scales its poller count with queue backlog automatically — no separate autoscaling policy to write, which is a meaningful chunk of "distributed worker pool" complexity that a traditional EC2/ECS worker-pool design (closer to how a crawler's fetcher fleet is usually described) would have to build by hand. `reservedConcurrentExecutions: 50` in the CDK stack caps how many can run at once — not for cost (this workload is small, per §3) but to cap the blast radius on Postgres (see §9, the real bottleneck) and on Open-Meteo's rate limits.

**Cold starts & the model cache**: `server/app/services/conditions.py`'s `_load_model_bundle()` already caches the deserialized model bundle in a module-level global for "the process lifetime" (added in spec 007 for the always-on server). Lambda's execution-environment reuse means that same cache works here **unmodified** — a cold start pays the one S3 fetch, every subsequent warm invocation of that same execution environment reuses the in-memory bundle for free. This is a case where a design decision made for a different deployment target (spec 007's always-on server) happened to be exactly right for this one too.

**The local-disk dependency this section used to work around no longer exists.** An earlier version of this design had `conditions.py`'s `_load_description()` reading a trail's enriched description from a local JSON file (`ENRICHED_DESCRIPTIONS_DIR/{trail_id}.json`) — fine for the Docker deployment (a bind-mounted host volume, spec 007), but Lambda has no host filesystem to mount, only an empty, ephemeral `/tmp` per execution environment. The original fix here was to sync descriptions to S3 alongside the model and fetch-and-cache them in `/tmp` on demand, mirroring the model's own caching pattern.

That workaround has since been superseded by the real fix it originally set aside as out of scope: `_load_description()` was migrated to read the `trails` table directly (`server/db/migrations/0004_add_model_terrain_features.sql` added the three terrain sub-fields the model needs that weren't already columns; `flatten_description()` itself — the function shared with training, per constitution Principle II — is untouched, `_load_description` just reconstructs an equivalent dict from the DB row instead of a file). `weather.py`'s `_get_trail_location()` got the same treatment.

This is a strictly better outcome for this pipeline specifically: the Lambda already needs a Postgres connection for the activity/review-count lookup (§6.5), so descriptions riding on that same connection means **zero** S3/`/tmp` caching machinery for this data — no second bucket prefix to keep in sync, no per-trail cache-population logic in the handler at all. It also retroactively answers "what's the point of the database" more strongly than before: it's no longer just backing one narrow lookup, it's the source for both the confidence data and the trail's physical/terrain data the model itself consumes.

**Partial-batch failure handling**: the SQS event source is configured with `reportBatchItemFailures: true`. When a Lambda invocation processes a batch of 5 messages and 1 fails, it reports only that one message ID as failed — the other 4 are deleted from the queue as successful, and only the 1 failure goes back for retry. Without this, a single bad message in a batch would force the *entire batch* to be retried, silently re-processing 4 messages that already succeeded.

**Idempotency**: `DynamoDB PutItem` with no condition expression is an unconditional overwrite. Combined with SQS's at-least-once delivery guarantee (a message can be delivered more than once in rare cases), this means processing the same message twice just writes the same key twice — the second write simply replaces the first with an equivalent result (FR-006/SC-002). No idempotency token or conditional-write logic is needed because the operation is naturally idempotent: recomputing the same (trailId, date) prediction from the same model version and the same weather-forecast window (within the 30-minute cache TTL already in `conditions.py`) produces the same answer.

### 6.3 DynamoDB: on-demand capacity, no GSI (yet)

**On-demand (`PAY_PER_REQUEST`) billing** was chosen over provisioned capacity + autoscaling. At this workload's scale (§3), provisioned capacity would mean either over-provisioning for a burst that only happens once a night, or under-provisioning and getting throttled exactly when the nightly batch runs — on-demand sidesteps that trade entirely for a workload this size and this bursty. (If this became a continuous, predictable high-throughput system instead of a nightly-batch-shaped one, provisioned + autoscaling would likely be cheaper — see §9.)

**No secondary index** is defined. The only query pattern this feature needs is point lookup / range-by-date-per-trail, both served by the base table's partition+sort key. Adding a GSI "just in case" for a query pattern nothing requires yet would be exactly the kind of speculative infrastructure this project's own conventions (and constitution Principle X, on not reaching for a structure the current requirement doesn't call for) argue against.

### 6.4 Dead-letter queue & alerting

`maxReceiveCount: 5` on the main queue's redrive policy means a message is retried up to 5 times (each retry gated by the visibility timeout) before SQS automatically moves it to the DLQ — no custom retry-counting code needed. A CloudWatch alarm on the DLQ's `ApproximateNumberOfMessagesVisible` metric (`>= 1` messages) fires an SNS notification (email, in this stack) the first time *anything* lands there, satisfying FR-009/SC-007 without needing a human to go looking for it.

One deliberate non-refinement, called out honestly rather than hidden: this design does not distinguish "permanently invalid input" (e.g. a malformed date — will never succeed no matter how many times it's retried) from "transient failure" (e.g. Open-Meteo rate-limited this one call) at the point of failure. Both are reported as a batch item failure and go through the same 5-retry redrive policy before reaching the DLQ. A more sophisticated version could inspect the exception type in the handler and route permanent failures (like a validation `HTTPException`) directly to the DLQ via an explicit `SendMessage` + `DeleteMessage`, skipping the wasted retries — left as a documented future refinement (§10) rather than built now, since it adds real complexity (manual DLQ redrive bypasses SQS's own accounting) for a workload where wasted retries cost a few extra Lambda invocations, not a meaningful amount of money or time at this scale.

### 6.5 Networking, the database, and secrets

**The database problem this section originally punted on is now solved**: the Lambda runs in AWS and has no path to spec 007's local docker-compose Postgres — that's not a networking detail to hand-wave, it means the pipeline simply cannot function without its own database. This stack provisions one directly (FR-015/FR-016), rather than assuming an externally-reachable database exists.

**A single db.t3.micro RDS Postgres instance — not Aurora Serverless v2, despite Aurora being the better fit on paper.** A fixed instance runs 24/7 whether or not anything is using it — at odds with this whole design's justification (§3, and `DESIGN_JUSTIFICATION.md`): pay for compute only when there's work. Aurora Serverless v2 was the original choice specifically because its capacity scales down after a period of no connections, so the database's cost would follow the same bursty, mostly-idle shape as everything else in this pipeline.

**That choice didn't survive contact with a real deploy.** Attempting `cdk deploy` against the target AWS account failed at `AWS::RDS::DBCluster` with: *"To use Aurora clusters with free plan accounts you need to set WithExpressConfiguration. To remove all limitations, upgrade your account plan."* This is an account-tier restriction enforced by the RDS API itself, not a CDK configuration problem — `aws-cdk-lib` (checked at 2.267.0) has no property anywhere in its RDS module corresponding to `WithExpressConfiguration`, so there's no typed way to satisfy it, and guessing at an untyped `addPropertyOverride` for an undocumented flag isn't a reasonable thing to ship. The pragmatic fix was to drop Aurora entirely: a plain `db.t3.micro` RDS Postgres instance is both RDS-Free-Tier-eligible (Aurora specifically isn't) and, at this workload's scale, actually cheaper in raw dollars than Aurora Serverless v2's per-ACU pricing floor — the "pay for what you use" argument still holds, just via a different, less elegant mechanism (a small fixed instance that's already cheap, rather than a scaling one). The loss: it doesn't scale down further if usage drops below db.t3.micro's baseline the way Aurora Serverless v2 would have. Worth revisiting if this ever runs on an AWS account without the free-plan restriction.

**Three-tier VPC**: public (holds the NAT Gateway), private-with-egress (the Lambda — needs outbound internet for Open-Meteo, which is outside AWS and has no VPC endpoint), and private-isolated (the database — no route to the internet at all, reachable only from inside the VPC). `vpc.addGatewayEndpoint` for S3 and DynamoDB routes that traffic for free instead of through the NAT Gateway, which only exists at all because Open-Meteo requires general internet egress that no AWS-service endpoint can substitute for.

**Access control has two independent layers** (FR-016: not password-only): a security group rule (`database.connections.allowDefaultPortFrom(predictionWorker, ...)`) that only permits inbound traffic on Postgres's port from the Lambda's own security group, and the credential itself. Being on the right network is necessary but not sufficient, and vice versa.

**Secrets**: the RDS instance's `Credentials.fromGeneratedSecret` creates a Secrets Manager secret containing only `{username, password}` — host, port, and database name aren't secret, so they're passed as plain Lambda environment variables instead of duplicating them into the secret for no security benefit. `handler.py` reads the secret once per execution environment (cold start), builds `DATABASE_URL` by combining it with those plain values, and caches it in the process environment for that environment's lifetime — same "pay once per warm container" shape as the model fetch (FR-014). The Lambda's IAM role is granted `secretsmanager:GetSecretValue` scoped to that one secret's ARN, nothing broader. That one `DATABASE_URL` now backs every Postgres-sourced read this Lambda makes — activity counts and, since §6.2's migration, trail descriptions too.

**What this doesn't solve**: provisioning the database's *infrastructure* isn't the same as populating it with *data* — the existing `server/db/backfill.py` still needs to be pointed at this new instance's endpoint manually (see `aws/README.md`). This stack also doesn't migrate the existing synchronous server (spec 007) onto this same database — see spec 008's Assumptions for why that's a deliberate, separate decision.

## 7. Fault Tolerance & Failure Modes

| Failure | Handling |
|---|---|
| Model S3 object unreachable/missing/corrupted | `_fetch_model_bundle_from_s3` (spec 007) raises a clear error; the Lambda invocation fails, message is retried (transient) up to 5 times, then DLQ + alarm |
| Trail's enriched description missing from S3 | `_ensure_description_cached` fails to download; treated the same as any other processing failure — retried, then DLQ |
| Postgres unreachable (activity lookup) | `get_trail_activity` raises; propagates as a processing failure — retried, then DLQ. A sustained DB outage will visibly pile up the DLQ and fire the alarm quickly, which is the intended signal that something systemic (not per-message) is wrong |
| Open-Meteo rate-limited or erroring | Already handled inside `conditions.py` as a 503/502 `HTTPException` (spec 001/005) — surfaces as a processing failure here the same way |
| Malformed SQS message body (not valid JSON, missing fields) | Caught explicitly in the handler, reported as a batch item failure — will exhaust its retries and dead-letter since it can never succeed |
| Lambda times out mid-processing | SQS's visibility timeout expiring re-delivers the message to another worker automatically — no special handling needed, this is exactly what the visibility timeout is for |
| A burst far exceeds concurrency limits | Messages simply wait longer in the queue (SQS has no practical size limit for this) — degrades to higher latency, not lost messages or errors, as long as `reservedConcurrentExecutions` and the account's Lambda concurrency ceiling aren't treated as a hard promise of a specific drain time |

## 8. Monitoring & Alerting

Built into the CDK stack:
- **DLQ depth alarm** (`ApproximateNumberOfMessagesVisible >= 1`) → SNS → email. The primary "something is wrong" signal (FR-009).
- **Lambda error-count alarm** (`>= 5` errors / 5 min) → SNS → email. Catches a systemic failure (e.g. a bad deploy, or every invocation erroring) faster than waiting for messages to exhaust their DLQ retries.

Worth adding as this matures (not built into the initial stack, to keep it focused):
- **Age of oldest message** (`ApproximateAgeOfOldestMessage` on the main queue) — the standard "is my consumer keeping up with my producer" signal; a growing value means the worker fleet is falling behind the backlog.
- **Lambda p99 duration** — an early warning that per-invocation work (e.g. Open-Meteo latency) is creeping up before it starts causing timeouts.
- **DynamoDB throttled requests** — should be near-impossible on-demand mode at this scale, but worth having as a canary if usage ever grows far beyond §3's estimate.

## 9. Bottlenecks & Scaling Limits

The honest answer to "what breaks first if this got 100x bigger":

- **Postgres connection exhaustion, not Lambda or DynamoDB.** `db/connection.py` opens a fresh `psycopg2.connect()` per call. At `reservedConcurrentExecutions: 50`, worst case is 50 concurrent connections — a `db.t3.micro`'s default `max_connections` (typically ~110 for its RAM size) covers that with headroom, but at real scale (hundreds/thousands of concurrent Lambda invocations, which Lambda itself scales to easily), this would exhaust the connection limit long before Lambda or DynamoDB became a constraint, and long before the instance's compute/storage would need upsizing. The standard fix is **RDS Proxy** in front of the instance (connection pooling/multiplexing so many Lambda invocations share a small pool of real DB connections) — not built into this stack because it only matters past the scale estimated in §3, but it's the first thing to add if this pipeline's volume grew an order of magnitude or more.
- **Open-Meteo's own rate limits** are an external dependency ceiling this design doesn't control — `reservedConcurrentExecutions` doubles as an implicit cap on how hard this pipeline hammers that API, which is a secondary reason it's set conservatively rather than left unbounded.
- **Lambda's account-level concurrency ceiling** (1,000 by default, raisable via support request) would only matter at a burst size roughly 20x larger than §3's estimate — worth knowing about, not worth engineering around preemptively.
- **DynamoDB hot partitions** aren't a concern at this item count/access pattern (point lookups spread across thousands of distinct `trailId` partition keys) — this would only become relevant if a single trail's key were hit at extreme, sustained request rates, which isn't this workload's shape.

## 10. Non-Goals / Future Work

- No HTTP read API is defined in front of the DynamoDB table in this feature (Assumptions, spec.md) — a future feature could add a thin read endpoint, or the existing FastAPI server could read from this table as a cache-check before falling back to synchronous computation.
- No retention/TTL policy for stored predictions — DynamoDB's native TTL attribute would be a natural fit once a staleness policy is decided (predictions are weather-dependent and age quickly).
- No RDS Proxy in this initial stack (§6.5, §9) — the database itself is now AWS-hosted and VPC-isolated, but connection pooling in front of it is the next thing to add once Lambda concurrency grows past what direct `psycopg2.connect()` per invocation can sustain.
- No automated data migration/sync between spec 007's local docker-compose Postgres and this feature's RDS instance — `server/db/backfill.py` must be pointed at the new instance manually (see `aws/README.md`), and the two databases can drift independently unless an operator deliberately keeps them in sync.
- Revisit Aurora Serverless v2 if this ever runs on an AWS account without the free-plan restriction that blocked it here (§6.5) — it remains the better-justified choice for this workload's bursty shape, the account, not the architecture, is what ruled it out.
- No distinction between permanent and transient failures at the retry level (§6.4) — a refinement, not a correctness requirement, given this workload's failure volume.
