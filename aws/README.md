# Async Serverless Trail-Conditions Inference (AWS)

Real, deployable infrastructure for [specs/008-aws-async-inference](../specs/008-aws-async-inference/spec.md) — an SQS → Lambda → DynamoDB pipeline that computes trail-conditions predictions asynchronously, at scale, alongside (not replacing) the existing synchronous `/conditions` endpoint from [specs/007-docker-containerization](../specs/007-docker-containerization/spec.md).

**Read [SYSTEM_DESIGN.md](./SYSTEM_DESIGN.md) first** — it explains every design decision below (why a container-image Lambda, why standard SQS not FIFO, why on-demand DynamoDB, how the Lambda gets trail description data without a filesystem, what breaks first at scale, etc.). For the same argument without the technical depth, see [DESIGN_JUSTIFICATION.md](./DESIGN_JUSTIFICATION.md).

## What's here

```
aws/
├── SYSTEM_DESIGN.md         # requirements, capacity estimate, architecture, deep dive, bottlenecks
├── DESIGN_JUSTIFICATION.md  # the same argument, in plain language
├── README.md                # this file - how to actually deploy it (CDK instructions below)
├── cdk/                 # the CDK app (TypeScript) that provisions everything - this README covers it
│   ├── bin/aws.ts        # entry point, reads deploy-time context
│   └── lib/inference-stack.ts  # SQS + DLQ, DynamoDB table, Lambda, alarms, IAM
├── terraform/            # equivalent provisioning in Terraform/HCL - see terraform/README.md
│   ├── vpc.tf, database.tf, queue.tf, dynamodb.tf, lambda.tf, alerts.tf, outputs.tf
│   └── README.md          # how it differs from the CDK version, and the naming-collision note
└── lambda/               # the worker's container image - shared by both CDK and Terraform
    ├── Dockerfile         # reuses server/app + server/db unmodified
    └── handler.py         # SQS batch handler
```

**Two provisioning tools, one identical architecture**: `cdk/` and `terraform/` both deploy the exact same resources (same names, same fixes learned from real deploy attempts — see the "Revision note" in [specs/008-aws-async-inference/plan.md](../specs/008-aws-async-inference/plan.md)). Use whichever tool you prefer; don't run both against the same AWS account at once — they'd collide on resource names by design. `terraform/README.md` has the switch-over steps if you're moving from one to the other.

## Deploying this creates real, billed AWS resources

Running `cdk deploy` provisions a VPC (with one NAT Gateway), an RDS Postgres instance (`db.t3.micro`), an SQS queue + DLQ, a DynamoDB table, a Lambda function, an SNS topic, and CloudWatch alarms in whatever AWS account/region your credentials point at. Review the stack (`cdk diff` / `cdk synth`) before deploying, and remember `cdk destroy` when you're done experimenting.

**Cost note**: the NAT Gateway and the RDS instance are the two components with an ongoing cost even at low/no traffic (both bill hourly regardless of usage). Everything else follows the workload closely enough to be very cheap at the scale estimated in SYSTEM_DESIGN.md §3. (An earlier version of this stack used Aurora Serverless v2 for its scale-to-near-zero cost profile, which is a better fit for this workload in principle — but the target AWS account's plan rejects Aurora cluster creation outright, so a plain instance is what's actually deployed; see SYSTEM_DESIGN.md §6.5.)

## Prerequisites

1. **AWS credentials** configured locally (`aws configure`, or an SSO profile) with permission to create the resources above (this now includes VPC/EC2 and RDS permissions, not just SQS/Lambda/DynamoDB).
2. **Node.js 20+** and **Docker** (Docker is used by CDK to build the Lambda's container image asset at deploy time — the same Docker Desktop setup from spec 007 works here too).
3. **An S3 bucket already holding** `condition_models.joblib` at the key you'll pass as `modelS3Key` (defaults to `condition_models.joblib`) — the same artifact spec 007's server container fetches. Trail descriptions no longer need a copy here (see SYSTEM_DESIGN.md §6.2) — `conditions.py` now reads them from the same RDS database this stack provisions.
4. **CDK bootstrapped** in the target account/region (one-time per account/region):
   ```bash
   npx cdk bootstrap
   ```

No database setup step is needed beforehand — this stack provisions its own RDS Postgres instance (see SYSTEM_DESIGN.md §6.5), you just need to populate it with data *after* deploying (see below).

## Deploy

```bash
cd aws/cdk
npm install
npx cdk synth \
  -c modelBucketName=YOUR-BUCKET \
  -c alertEmail=you@example.com
# review the synthesized template, then:
npx cdk deploy \
  -c modelBucketName=YOUR-BUCKET \
  -c alertEmail=you@example.com
```

Confirm the SNS email subscription (check your inbox) so the DLQ-depth/worker-error alarms actually reach you.

## Populate the database

`cdk deploy` provisions an empty RDS instance — schema and data still need to be applied, the same way they're applied to the local docker-compose Postgres in spec 007. The deploy output includes `DatabaseEndpoint` and `DatabaseCredentialsSecretArn`:

```bash
# Get the generated username/password:
aws secretsmanager get-secret-value --secret-id "$DATABASE_CREDENTIALS_SECRET_ARN" --query SecretString --output text

# Apply the existing schema (from spec 002/003) against the new database:
psql "postgresql://USERNAME:PASSWORD@$DATABASE_ENDPOINT:5432/cairns" -f server/db/migrations/0001_trail_data_storage.sql
psql "postgresql://USERNAME:PASSWORD@$DATABASE_ENDPOINT:5432/cairns" -f server/db/migrations/0002_add_trail_image.sql
psql "postgresql://USERNAME:PASSWORD@$DATABASE_ENDPOINT:5432/cairns" -f server/db/migrations/0003_add_trail_area_name.sql
psql "postgresql://USERNAME:PASSWORD@$DATABASE_ENDPOINT:5432/cairns" -f server/db/migrations/0004_add_model_terrain_features.sql

# Then backfill trail data the same way you would locally:
DATABASE_URL="postgresql://USERNAME:PASSWORD@$DATABASE_ENDPOINT:5432/cairns" \
  python -m db.backfill
```

The RDS instance is in an isolated private subnet (SYSTEM_DESIGN.md §6.5) — `psql`/`python` need to run from somewhere with network access to it (a bastion host, an EC2 instance in the same VPC, or a temporarily-opened security group rule for your IP; this stack doesn't set up a bastion, since it's a one-time setup step, not part of the running pipeline).

## Try it

After `cdk deploy` finishes, it prints `RequestQueueUrl` and `PredictionsTableName` as outputs.

```bash
# Submit a request (use a real trailId that exists in your backfilled data)
aws sqs send-message \
  --queue-url "$REQUEST_QUEUE_URL" \
  --message-body '{"trailId": "99887766", "date": "2026-09-15"}'

# A few seconds later, check the result:
aws dynamodb get-item \
  --table-name cairns-trail-conditions-predictions \
  --key '{"trailId": {"S": "99887766"}, "date": {"S": "2026-09-15"}}'
```

To see failure handling, submit a request with an invalid date or a trailId that has no enriched description in S3 — after 5 retries it lands in the dead-letter queue and you should get an email alert.

## Tear down

```bash
npx cdk destroy \
  -c modelBucketName=YOUR-BUCKET \
  -c alertEmail=you@example.com
```

The DynamoDB table has `RemovalPolicy.RETAIN` (see `lib/inference-stack.ts`), so it survives a stack destroy on purpose — delete it manually if you actually want the stored predictions gone. The RDS instance, by contrast, is set to `RemovalPolicy.DESTROY` for easy iteration (see the comment in `lib/inference-stack.ts`) — `cdk destroy` really does delete it and its data, so back up anything you care about first if you've been using it for more than a quick test.
