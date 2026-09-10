output "request_queue_url" {
  value = aws_sqs_queue.requests.url
}

output "dead_letter_queue_url" {
  value = aws_sqs_queue.dlq.url
}

output "predictions_table_name" {
  value = aws_dynamodb_table.predictions.name
}

output "alert_topic_arn" {
  value = aws_sns_topic.alerts.arn
}

output "database_endpoint" {
  value = aws_db_instance.trails.address
}

output "database_credentials_secret_arn" {
  description = "Fetch with `aws secretsmanager get-secret-value` to run server/db/backfill.py against this database - see aws/README.md."
  value       = aws_secretsmanager_secret.db.arn
}

output "ecr_repository_url" {
  value = aws_ecr_repository.prediction_worker.repository_url
}
