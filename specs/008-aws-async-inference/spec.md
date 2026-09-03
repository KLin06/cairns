# Feature Specification: Async Serverless Model Inference at Scale (SQS + Lambda + DynamoDB)

**Feature Branch**: `008-aws-async-inference`

**Created**: 2026-08-30

**Status**: Draft

**Input**: User description: "I want it to be actually deployed so modify the spec (I want it to be usable but I actually run it at scale), also can you explain the infrastructure. I want it to have the systems design logic similar to the crawler in Grokking the System Design Interview. Put the documentation in a new folder called aws where you will write the code for the cdk." (Supersedes this feature's original POC-only framing: this pipeline is now a real, deployed, horizontally-scaling production system, built and provisioned via AWS CDK, documented with system-design-interview-style reasoning — requirements, capacity estimation, component tradeoffs, bottlenecks, fault tolerance — in `aws/`.)

## Scope Note

This feature is a **real, deployable production system**, not a design exercise — its CDK code (in `aws/cdk/`) is meant to actually provision SQS, Lambda, and DynamoDB resources in an AWS account and process real traffic at scale. It runs alongside, and does not replace or modify, the existing synchronous `/trails/{trail_id}/conditions` endpoint from [specs/007-docker-containerization](../007-docker-containerization/spec.md) — that endpoint remains the low-latency, single-prediction path; this pipeline is a horizontally-scaling path for bulk/asynchronous demand (e.g. precomputing predictions for many trails/dates at once, or absorbing bursty load without scaling the always-on server). Deploying it (running `cdk deploy`) is a deliberate, explicit action the operator takes with their own AWS account and credentials — this spec and its design/code artifacts do not themselves deploy anything.

## User Scenarios & Testing *(mandatory)*

### User Story 1 - Submit a prediction request for asynchronous, high-throughput processing (Priority: P1)

An operator or an upstream system wants to request trail-conditions predictions — potentially many at once (e.g. every trail for the next 16 days) — without waiting for each to be computed inline, and without that burst of demand overwhelming the always-on synchronous server.

**Why this priority**: This is the entry point of the whole pipeline and the reason it exists — absorbing bulk/bursty demand that the synchronous path isn't sized for.

**Independent Test**: Submitting a large batch of valid requests (trail ID + date) to the queue results in all of them eventually being processed, with the compute layer scaling out to handle the burst rather than processing them one at a time.

**Acceptance Scenarios**:

1. **Given** a request describing a valid trail ID and a date within the existing forecast horizon, **When** it is submitted to the queue, **Then** the compute layer picks it up and begins processing without any caller having to wait synchronously for a result.
2. **Given** a large burst of requests is submitted at once (far more than one compute worker could process serially in a reasonable time), **When** they are submitted, **Then** the compute layer scales out concurrently to drain the backlog, and no request is dropped for lack of capacity.
3. **Given** the compute layer is temporarily unavailable or at its concurrency ceiling, **When** a request is submitted, **Then** the request remains queued and is picked up once capacity is available, rather than being lost.

---

### User Story 2 - Compute the prediction and persist it for later retrieval (Priority: P1)

A downstream consumer wants a previously requested prediction to be durably available for retrieval afterward, without needing to recompute it, computed using the same model and feature logic as the existing synchronous endpoint so the two paths agree on results for the same inputs.

**Why this priority**: This is the value the pipeline actually delivers — a computed, retrievable, correct result at scale.

**Independent Test**: After a queued request has been processed, a resulting record appears in persistent storage keyed by the same trail ID and date, containing the same shape of prediction data the synchronous endpoint returns today, retrievable without recomputation.

**Acceptance Scenarios**:

1. **Given** a queued request for a trail ID and date, **When** the compute layer finishes processing it, **Then** a record containing the computed conditions prediction is stored, retrievable later by that same trail ID and date, at low, predictable read latency regardless of overall system load.
2. **Given** a prediction has already been computed and stored for a given trail ID and date, **When** the same request is processed again, **Then** the stored record is updated/replaced rather than accumulating duplicate, ambiguous records for the same key.
3. **Given** the compute layer's model source is unavailable when it tries to process a request, **When** that failure occurs, **Then** no partial or fabricated prediction is stored for that request.

---

### User Story 3 - Failed requests are visible, not silently lost, at any volume (Priority: P1)

An operator wants to know when a queued request could not be processed (bad input, a model-loading failure, an unexpected error) so they can investigate, rather than have it vanish or retry forever and consume capacity — including when failures happen in bulk (e.g. the model source goes down mid-burst).

**Why this priority**: At real production scale, silent data loss or a retry storm consuming all compute capacity is a much bigger risk than in a one-off demo — this is promoted to P1 (from P2 in the original POC framing) because operability is not optional once this handles real traffic.

**Independent Test**: A request that cannot be processed (malformed input, or a compute step that errors on every attempt) ends up in a distinct, inspectable location after a bounded number of attempts, separate from successfully processed requests, and an operator is notified rather than needing to poll for it.

**Acceptance Scenarios**:

1. **Given** a request with input that cannot be processed (e.g. missing/invalid trail ID or date), **When** the compute layer attempts it, **Then** it is set aside as failed rather than retried indefinitely.
2. **Given** a request repeatedly fails during processing (e.g. a transient dependency is down every attempt), **When** it has been retried a bounded number of times, **Then** it is moved to a distinct failed-requests location rather than continuing to consume processing capacity forever.
3. **Given** a request has landed in the failed-requests location, **When** an operator inspects it, **Then** enough information is present (the original request and some indication of what went wrong) to diagnose the failure without needing to reproduce it from scratch.
4. **Given** failed requests start accumulating (e.g. a dependency outage causes many requests to fail in a short window), **When** that accumulation crosses a meaningful threshold, **Then** an operator is actively alerted rather than needing to notice it themselves.

---

### Edge Cases

- What happens when a request for a date outside the model's valid forecast horizon is submitted? It MUST be treated as a failure case (per User Story 3), consistent with the existing synchronous endpoint's date-horizon rejection — not silently computed with a fabricated or out-of-range result.
- What happens when two requests for the same trail ID and date are submitted around the same time? The system MUST tolerate processing them concurrently without producing two conflicting stored records — the later write wins, per User Story 2's replace-not-duplicate behavior.
- What happens when the compute layer's model source (the same S3-hosted model artifact used by spec 007) is temporarily unreachable? This MUST be treated as a retryable failure (bounded retries, then dead-letter), not a permanent one, distinguishing it conceptually from a malformed request that will never succeed no matter how many times it's retried.
- What happens when demand spikes far beyond normal (e.g. 10x the typical burst)? The system MUST continue accepting and eventually processing requests (queue absorbs the spike) rather than rejecting submissions outright — see Success Criteria for the specific throughput/latency targets this must hold up to.
- What happens to a previously stored prediction if it is never explicitly requested again? Out of scope for this feature to specify an eviction/retention policy in detail — noted as an open question in Assumptions.
- What happens to the trail data (trail records, activity/review aggregates) the compute layer needs, given today it only exists in a developer's local database? This feature MUST provision its own reachable database as infrastructure, but populating it with real trail data (running the existing backfill process against it) is an operational step the operator performs afterward, not something this feature automates — see FR-015 and Assumptions.

## Requirements *(mandatory)*

### Functional Requirements

- **FR-001**: The system MUST provide a request format for submitting an asynchronous prediction request that carries at minimum a trail identifier and a target date, matching the inputs already accepted by the existing synchronous conditions endpoint.
- **FR-002**: The system MUST provide a queuing mechanism that holds submitted requests until they are picked up for processing, without requiring the submitter to wait for processing to complete, and that can absorb bursts far larger than the compute layer's steady-state processing rate.
- **FR-003**: The system MUST provide a compute layer that, for each request it picks up, produces a conditions prediction using the same model artifact and the same feature-assembly logic as the existing synchronous `/conditions` endpoint (per [Principle II](../../.specify/memory/constitution.md) of the project constitution: training/inference feature parity) — reused directly, not reimplemented separately for this pipeline.
- **FR-004**: The compute layer MUST scale out automatically as queue backlog grows and back in as it drains, without manual operator intervention.
- **FR-005**: The system MUST provide durable, keyed storage for computed predictions such that a prediction for a given trail ID and date can be retrieved later without recomputing it, at low and predictable read latency independent of overall system load.
- **FR-006**: Storing a new prediction for a trail ID/date combination that was already stored MUST replace the prior record for that same key, not create an additional, ambiguous entry.
- **FR-007**: The system MUST route a request that cannot be successfully processed (invalid input, or repeated processing failure) into a distinct, inspectable location after a bounded number of attempts, rather than retrying it indefinitely or silently dropping it.
- **FR-008**: The system MUST retain, for each failed request, enough information for an operator to diagnose why it failed without needing to reproduce the failure.
- **FR-009**: The system MUST alert an operator when failed requests accumulate past a meaningful threshold, rather than requiring active polling to notice.
- **FR-010**: This pipeline MUST NOT modify, replace, or require changes to the existing synchronous `/conditions` endpoint — the two paths coexist.
- **FR-011**: The system MUST be defined as infrastructure-as-code (AWS CDK) such that it can be deployed, updated, and torn down repeatably rather than being hand-configured in the AWS console.
- **FR-012**: The system MUST reject (route to the failed-requests location) a request for a date outside the valid forecast horizon, consistent with the existing synchronous endpoint's rejection behavior, so the two paths don't silently disagree on what's a valid request.
- **FR-013**: The system's components (queue, compute, storage) MUST each be independently scalable — a spike in submission volume must not require manually resizing storage, and storage throughput must not become a bottleneck on compute concurrency.
- **FR-014**: Credentials and connection details the compute layer needs (database access, AWS credentials/role) MUST NOT be stored in plaintext in the infrastructure code or in the compute layer's deployed configuration — they MUST come from a managed secrets store.
- **FR-015**: The system MUST provision its own reachable database as part of its infrastructure-as-code, rather than assuming an already-existing, externally-managed database is reachable. The compute layer runs in AWS and has no network path to a database that exists only on a developer's local machine (e.g. spec 007's local docker-compose Postgres) — this feature closes that gap rather than leaving it as an unstated dependency.
- **FR-016**: The database provisioned by FR-015 MUST NOT be reachable from the open internet on a password alone — the compute layer MUST reach it over private networking, with network-level access control as a second layer beyond credentials.

### Key Entities

- **Prediction Request**: A submitted request to compute conditions for a specific trail on a specific date. Carries trail ID and date (mirroring the existing synchronous endpoint's inputs) and exists transiently in the queue until processed.
- **Stored Prediction**: The durable result of a successfully processed request — the same conditions/confidence/model-version data the synchronous endpoint returns today — keyed by trail ID and date, and replaceable by a later computation for the same key.
- **Failed Request Record**: A request that could not be successfully processed after a bounded number of attempts, retained along with enough context (the original request and failure information) for an operator to diagnose it.

## Success Criteria *(mandatory)*

### Measurable Outcomes

- **SC-001**: A burst of at least 1,000 prediction requests submitted at once is fully drained (every request either stored or dead-lettered) within a few minutes, without manual intervention or dropped requests.
- **SC-002**: Requesting the same trail/date twice never results in more than one ambiguous stored record for that key.
- **SC-003**: No request is ever silently lost — every submitted request either results in a stored prediction or a diagnosable failed-request record, and an operator is notified when failures accumulate.
- **SC-004**: A request for an out-of-horizon date is rejected the same way conceptually as the existing synchronous endpoint rejects it.
- **SC-005**: Retrieving an already-computed prediction consistently returns in well under a second, regardless of how much submission volume the system is concurrently absorbing.
- **SC-006**: The system — including the database it depends on (FR-015) — can be stood up, updated, and torn down entirely through the CDK code — no manually-clicked AWS console configuration is required to reproduce the deployed environment.
- **SC-007**: A sustained dependency outage (e.g. the model source becomes unreachable) results in operator notification within minutes of the failure threshold being crossed, not after the fact via manual discovery.

## Assumptions

- This feature builds and deploys real AWS infrastructure via CDK, but *actually running* `cdk deploy` against a live AWS account is an action the operator takes deliberately with their own credentials/account — this spec and its accompanying code do not themselves provision anything.
- The asynchronous pipeline reuses the same S3-hosted model artifact location as [specs/007-docker-containerization](../007-docker-containerization/spec.md) — this feature does not introduce a second model storage location or a different versioning scheme for the model.
- "Reused directly, not reimplemented" (FR-003) means the compute layer's deployment artifact packages and calls the existing `server/app/services/conditions.py` prediction logic (and its dependencies: feature flattening, weather fetch, trail data access) rather than re-deriving it independently — consistent with constitution Principle II.
- The compute layer needs the same inputs the synchronous endpoint needs today (trail static data, live weather, the model). Trail static data's storage location did change during this feature's implementation — descriptions moved from a local pipeline-output file to the `trails` table (`server/db/migrations/0004_add_model_terrain_features.sql`), so the compute layer could reach it via the same Postgres connection it already needs for activity data, without a filesystem or a second S3 prefix. That change was made to `server/app/services/conditions.py`/`weather.py` themselves (not just to this feature's own Lambda code), and strengthens rather than weakens FR-003/FR-010: both the synchronous and asynchronous paths now read trail data through the identical code path, closing a gap rather than opening one.
- Long-term retention/eviction policy for stored predictions (how long a computed result stays valid before it's considered stale, given weather-dependent predictions age quickly) is explicitly out of scope for this feature and is left as an open question rather than a resolved requirement.
- "A bounded number of attempts" and the specific alerting threshold (FR-009/SC-007) are operational parameters tuned in the CDK code/design doc rather than fixed by this spec as a business rule.
- No new user-facing surface (UI or public API) is introduced by this feature — retrieval of a stored prediction is described conceptually (User Story 2/3) but this spec does not define a new client-facing endpoint for it; that is a separate, later decision about whether/how to expose this path to the existing app.
- This feature provisions its own managed database (e.g. AWS RDS for Postgres) as part of its infrastructure-as-code (FR-015/FR-016) — it is a separate, AWS-hosted instance from spec 007's local docker-compose Postgres used for local development, not a way of reaching into a developer's machine. The specific private-networking approach (VPC subnets, and how the compute layer still reaches S3/DynamoDB/Open-Meteo from inside that VPC) is a design decision documented in `aws/SYSTEM_DESIGN.md`, not fixed by this spec.
- This feature provisions the database's infrastructure and schema reachability, not its data — populating the newly-provisioned database with real trail records/activity (via the existing `server/db/backfill.py`, pointed at the new database's connection string) is an operational step the operator performs, not something this feature automates.
- If a future production deployment of the existing synchronous server (spec 007) also moves off a local docker-compose Postgres, it should point at this same provisioned database rather than each feature provisioning its own, divergent copy of trail data — this feature doesn't implement that consolidation, but its database is designed to be reusable that way.
