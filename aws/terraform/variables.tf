variable "aws_region" {
  description = "AWS region to deploy into."
  type        = string
  default     = "us-east-1"
}

variable "model_bucket_name" {
  description = "Name of the existing S3 bucket holding condition_models.joblib (see specs/007-docker-containerization). Not created by this configuration - it must already exist and hold the model at model_s3_key."
  type        = string
}

variable "model_s3_key" {
  description = "S3 key of the model artifact within model_bucket_name."
  type        = string
  default     = "condition_models.joblib"
}

variable "alert_email" {
  description = "Email address subscribed to DLQ-depth / worker-error CloudWatch alarms."
  type        = string
}
