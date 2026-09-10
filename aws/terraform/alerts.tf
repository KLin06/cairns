# Fires the moment anything reaches the DLQ, or the worker starts erroring
# systemically, rather than relying on an operator to notice (FR-009/SC-007).

resource "aws_sns_topic" "alerts" {
  name = "cairns-prediction-alerts"
}

resource "aws_sns_topic_subscription" "alerts_email" {
  topic_arn = aws_sns_topic.alerts.arn
  protocol  = "email"
  endpoint  = var.alert_email
}

resource "aws_cloudwatch_metric_alarm" "dlq_depth" {
  alarm_name          = "cairns-prediction-dlq-depth"
  alarm_description   = "One or more prediction requests landed in the dead-letter queue after exhausting retries - see specs/008-aws-async-inference/spec.md FR-007/FR-009."
  comparison_operator = "GreaterThanOrEqualToThreshold"
  evaluation_periods  = 1
  metric_name         = "ApproximateNumberOfMessagesVisible"
  namespace           = "AWS/SQS"
  period              = 300
  statistic           = "Maximum"
  threshold           = 1
  treat_missing_data  = "notBreaching"

  dimensions = {
    QueueName = aws_sqs_queue.dlq.name
  }

  alarm_actions = [aws_sns_topic.alerts.arn]
}

resource "aws_cloudwatch_metric_alarm" "worker_errors" {
  alarm_name          = "cairns-prediction-worker-errors"
  alarm_description   = "The prediction worker Lambda is erroring on a significant share of invocations."
  comparison_operator = "GreaterThanOrEqualToThreshold"
  evaluation_periods  = 1
  metric_name         = "Errors"
  namespace           = "AWS/Lambda"
  period              = 300
  statistic           = "Sum"
  threshold           = 5
  treat_missing_data  = "notBreaching"

  dimensions = {
    FunctionName = aws_lambda_function.prediction_worker.function_name
  }

  alarm_actions = [aws_sns_topic.alerts.arn]
}
