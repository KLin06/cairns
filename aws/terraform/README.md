# Terraform (alternative to `aws/cdk/`)

A complete Terraform equivalent of `aws/cdk/lib/inference-stack.ts` — same resources, same names, same fixes (root `.dockerignore`, Python 3.12 base image, plain RDS instance instead of Aurora, no reserved Lambda concurrency). See [../SYSTEM_DESIGN.md](../SYSTEM_DESIGN.md) for the design reasoning; this is a different tool provisioning the identical architecture, not a different design.

## Before you apply: don't run this alongside the CDK stack

This configuration uses the **same resource names** as the CDK stack (`cairns-prediction-requests`, `cairns-trail-conditions-predictions`, `cairns-prediction-worker`, `cairns-prediction-alerts`) — that's deliberate, so the two are interchangeable, not so they coexist. If the CDK stack (`CairnsAsyncInferenceStack`) is still deployed, `terraform apply` will fail with `AlreadyExists` errors on every one of those.

To switch from CDK to Terraform:
```bash
cd ../cdk
npx cdk destroy -c modelBucketName=YOUR-BUCKET -c alertEmail=you@example.com
cd ../terraform
terraform apply -var="model_bucket_name=YOUR-BUCKET" -var="alert_email=you@example.com"
```

## What's different from the CDK version (Terraform has no equivalent)

- **Docker image build**: CDK's `DockerImageCode.fromImageAsset` builds and pushes the Lambda's image automatically. Terraform has no native resource for this — `lambda.tf`'s `null_resource.build_and_push_image` shells out to the `docker` and `aws` CLIs directly (`local-exec` provisioner). This means `terraform apply` must run somewhere with **Docker and the AWS CLI already on PATH** (same requirement as the CDK version), and it re-runs the build whenever `aws/lambda/Dockerfile`, `handler.py`, or `server/requirements.txt` change (tracked via file-hash triggers).
- **Local state**: this uses Terraform's default local backend (`terraform.tfstate` in this directory, gitignored). Fine for one operator; a team would want a remote backend (S3 + a DynamoDB lock table) instead — not set up here since it's outside the scope of converting the provisioning itself.

## Deploy

```bash
cd aws/terraform
terraform init
terraform plan  -var="model_bucket_name=YOUR-BUCKET" -var="alert_email=you@example.com"
terraform apply -var="model_bucket_name=YOUR-BUCKET" -var="alert_email=you@example.com"
```

Or put `model_bucket_name` / `alert_email` in a `terraform.tfvars` file (gitignored, matching `.gitignore`'s exception for `terraform.tfvars.example`) to avoid retyping `-var` flags every time.

Same prerequisites as `../README.md`: an S3 bucket already holding `condition_models.joblib`, and CDK's `cdk bootstrap`-equivalent step doesn't apply to Terraform (nothing extra needed beyond standard AWS credentials).

## Tear down

```bash
terraform destroy -var="model_bucket_name=YOUR-BUCKET" -var="alert_email=you@example.com"
```

The DynamoDB table has `lifecycle { prevent_destroy = true }` (`dynamodb.tf`) — mirroring the CDK stack's `RemovalPolicy.RETAIN` — so `terraform destroy` will refuse to remove it until you delete that lifecycle block (or `terraform state rm aws_dynamodb_table.predictions` first).

## Verified

`terraform validate` passes, and `terraform plan` against the real target AWS account (596152114380 / us-east-1) resolves cleanly — 44 resources to add, 0 errors — confirming every resource reference and attribute is valid against the real provider schema. `terraform apply` was deliberately **not** run, both because it would collide with the still-live CDK stack and because applying real infrastructure is something to do deliberately, not as a side effect of a conversion request.
