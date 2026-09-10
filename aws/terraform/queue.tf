# Standard queue, not FIFO - see aws/SYSTEM_DESIGN.md section 6.1 for why
# ordering/exactly-once don't matter for this workload.

resource "aws_sqs_queue" "dlq" {
  name                      = "cairns-prediction-requests-dlq"
  message_retention_seconds = 1209600 # 14 days
  sqs_managed_sse_enabled   = true
  tags                      = { Name = "cairns-prediction-requests-dlq" }
}

resource "aws_sqs_queue" "requests" {
  name = "cairns-prediction-requests"

  # Must exceed the Lambda's own timeout (90s, lambda.tf) with margin, so a
  # message isn't returned to the queue while still being processed.
  visibility_timeout_seconds = 180
  message_retention_seconds  = 345600 # 4 days
  sqs_managed_sse_enabled    = true

  redrive_policy = jsonencode({
    deadLetterTargetArn = aws_sqs_queue.dlq.arn
    maxReceiveCount     = 5
  })

  tags = { Name = "cairns-prediction-requests" }
}
