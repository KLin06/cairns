# On-demand billing: this workload is bursty/nightly-batch-shaped, not
# continuous - see aws/SYSTEM_DESIGN.md section 6.3.

resource "aws_dynamodb_table" "predictions" {
  name         = "cairns-trail-conditions-predictions"
  billing_mode = "PAY_PER_REQUEST"
  hash_key     = "trailId"
  range_key    = "date"

  attribute {
    name = "trailId"
    type = "S"
  }

  attribute {
    name = "date"
    type = "S"
  }

  point_in_time_recovery {
    enabled = true
  }

  tags = { Name = "cairns-trail-conditions-predictions" }

  # Mirrors the CDK stack's RemovalPolicy.RETAIN - stored predictions
  # shouldn't disappear just because the stack is torn down. Terraform's
  # equivalent, prevent_destroy, blocks `terraform destroy` for this
  # resource entirely; remove this lifecycle block (or `terraform state rm`
  # it first) if you actually want to delete the table.
  lifecycle {
    prevent_destroy = true
  }
}
