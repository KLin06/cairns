# Container image, not zip/layers - scikit-learn + pandas + joblib are well
# past the 250MB zip limit. Reuses server/app + server/db unmodified (see
# aws/lambda/Dockerfile), per constitution Principle II / spec 008 FR-003.

resource "aws_ecr_repository" "prediction_worker" {
  name                 = "cairns-prediction-worker"
  image_tag_mutability = "MUTABLE"
  force_delete         = true # POC-friendly - allows `terraform destroy` even with images still pushed
  tags                 = { Name = "cairns-prediction-worker" }
}

# Terraform has no native "build and push a Docker image" resource (unlike
# CDK's DockerImageCode.fromImageAsset, which does this automatically) - the
# standard pattern is a null_resource shelling out to the docker CLI.
# Requires Docker and the AWS CLI on PATH wherever `terraform apply` runs.
resource "null_resource" "build_and_push_image" {
  triggers = {
    dockerfile_hash   = filemd5("${path.module}/../lambda/Dockerfile")
    handler_hash      = filemd5("${path.module}/../lambda/handler.py")
    requirements_hash = filemd5("${path.module}/../../server/requirements.txt")
  }

  provisioner "local-exec" {
    # Build context is the repo root (see the root .dockerignore - without
    # it, this stages the entire repo, including node_modules/venv/.git,
    # before docker build ever runs - a real bug hit and fixed during the
    # CDK version's first real deploy attempt).
    working_dir = "${path.module}/../.."
    interpreter = ["bash", "-c"]
    command     = <<-EOT
      set -euo pipefail
      aws ecr get-login-password --region ${var.aws_region} | docker login --username AWS --password-stdin ${aws_ecr_repository.prediction_worker.repository_url}
      docker build -f aws/lambda/Dockerfile -t ${aws_ecr_repository.prediction_worker.repository_url}:latest .
      docker push ${aws_ecr_repository.prediction_worker.repository_url}:latest
    EOT
  }

  depends_on = [aws_ecr_repository.prediction_worker]
}

data "aws_iam_policy_document" "lambda_assume" {
  statement {
    actions = ["sts:AssumeRole"]
    principals {
      type        = "Service"
      identifiers = ["lambda.amazonaws.com"]
    }
  }
}

resource "aws_iam_role" "lambda" {
  name               = "cairns-prediction-worker-role"
  assume_role_policy = data.aws_iam_policy_document.lambda_assume.json
}

resource "aws_iam_role_policy_attachment" "lambda_basic" {
  role       = aws_iam_role.lambda.name
  policy_arn = "arn:aws:iam::aws:policy/service-role/AWSLambdaBasicExecutionRole"
}

# Required for the Lambda to create/manage ENIs in the VPC - CDK grants this
# automatically when a Function has vpc config; Terraform needs it explicit.
resource "aws_iam_role_policy_attachment" "lambda_vpc" {
  role       = aws_iam_role.lambda.name
  policy_arn = "arn:aws:iam::aws:policy/service-role/AWSLambdaVPCAccessExecutionRole"
}

# Least-privilege grants (FR-014) - no wildcard resource ARNs.
data "aws_iam_policy_document" "lambda_permissions" {
  statement {
    sid       = "ReadModelBucket"
    actions   = ["s3:GetObject"]
    resources = ["arn:aws:s3:::${var.model_bucket_name}/${var.model_s3_key}"]
  }

  statement {
    sid       = "WritePredictions"
    actions   = ["dynamodb:PutItem", "dynamodb:UpdateItem", "dynamodb:BatchWriteItem"]
    resources = [aws_dynamodb_table.predictions.arn]
  }

  statement {
    sid       = "ReadDbSecret"
    actions   = ["secretsmanager:GetSecretValue"]
    resources = [aws_secretsmanager_secret.db.arn]
  }

  statement {
    sid       = "ConsumeRequestQueue"
    actions   = ["sqs:ReceiveMessage", "sqs:DeleteMessage", "sqs:GetQueueAttributes"]
    resources = [aws_sqs_queue.requests.arn]
  }
}

resource "aws_iam_role_policy" "lambda_permissions" {
  name   = "cairns-prediction-worker-permissions"
  role   = aws_iam_role.lambda.id
  policy = data.aws_iam_policy_document.lambda_permissions.json
}

resource "aws_security_group" "lambda" {
  name        = "cairns-prediction-worker-sg"
  description = "Prediction worker Lambda"
  vpc_id      = aws_vpc.inference.id

  egress {
    from_port   = 0
    to_port     = 0
    protocol    = "-1"
    cidr_blocks = ["0.0.0.0/0"]
  }

  tags = { Name = "cairns-prediction-worker-sg" }
}

resource "aws_lambda_function" "prediction_worker" {
  function_name = "cairns-prediction-worker"
  role          = aws_iam_role.lambda.arn
  package_type  = "Image"
  image_uri     = "${aws_ecr_repository.prediction_worker.repository_url}:latest"
  memory_size   = 1024
  timeout       = 90

  # No reserved_concurrent_executions: this account's total Lambda
  # concurrency ceiling is low enough that reserving any meaningful amount
  # violated AWS's "at least 10 unreserved for the rest of the account"
  # rule - a real-deploy discovery (same restricted-account theme as the
  # Aurora rejection above), not a design choice.

  # Must run where it can reach the isolated-subnet database (FR-015) - the
  # lambda-private tier also gives it a path to Open-Meteo via the NAT
  # Gateway, and to S3/DynamoDB via the gateway endpoints in vpc.tf.
  vpc_config {
    subnet_ids         = aws_subnet.lambda_private[*].id
    security_group_ids = [aws_security_group.lambda.id]
  }

  environment {
    variables = {
      MODEL_S3_BUCKET           = var.model_bucket_name
      MODEL_S3_KEY              = var.model_s3_key
      PREDICTIONS_TABLE_NAME    = aws_dynamodb_table.predictions.name
      DB_CREDENTIALS_SECRET_ARN = aws_secretsmanager_secret.db.arn
      DB_HOST                   = aws_db_instance.trails.address
      DB_PORT                   = tostring(aws_db_instance.trails.port)
      DB_NAME                   = "cairns"
    }
  }

  depends_on = [
    null_resource.build_and_push_image,
    aws_iam_role_policy.lambda_permissions,
    aws_iam_role_policy_attachment.lambda_vpc,
    aws_iam_role_policy_attachment.lambda_basic,
  ]

  tags = { Name = "cairns-prediction-worker" }
}

# A bad message in a batch of 5 shouldn't force the other 4 (which may have
# already succeeded) to be reprocessed - see aws/SYSTEM_DESIGN.md 6.2.
resource "aws_lambda_event_source_mapping" "sqs_trigger" {
  event_source_arn        = aws_sqs_queue.requests.arn
  function_name           = aws_lambda_function.prediction_worker.arn
  batch_size              = 5
  function_response_types = ["ReportBatchItemFailures"]
}
