# Plain single-instance RDS Postgres, not Aurora Serverless v2 - Aurora was
# the original choice for its pay-for-what-you-use scaling (see
# SYSTEM_DESIGN.md / DESIGN_JUSTIFICATION.md), but a real deploy attempt
# against the target AWS account rejected Aurora cluster creation outright
# ("free plan accounts" require an undocumented "WithExpressConfiguration"
# flag with no equivalent property in either aws-cdk-lib or the Terraform
# AWS provider - an account-level restriction, not a tooling gap). A
# db.t3.micro instance is both RDS-Free-Tier-eligible (Aurora isn't) and
# cheaper in raw dollars than Aurora Serverless v2's ACU pricing floor at
# this workload's tiny scale.

resource "random_password" "db" {
  length  = 32
  special = false # avoids any character that would need escaping in a postgresql:// URL
}

resource "aws_secretsmanager_secret" "db" {
  name = "cairns-trails-db-credentials"
}

resource "aws_secretsmanager_secret_version" "db" {
  secret_id = aws_secretsmanager_secret.db.id
  secret_string = jsonencode({
    username = "cairns_app"
    password = random_password.db.result
  })
}

resource "aws_db_subnet_group" "trails" {
  name       = "cairns-trails-db-subnet-group"
  subnet_ids = aws_subnet.database_isolated[*].id
  tags       = { Name = "cairns-trails-db-subnet-group" }
}

resource "aws_security_group" "database" {
  name        = "cairns-trails-db-sg"
  description = "Postgres - reachable only from the prediction worker Lambda's security group"
  vpc_id      = aws_vpc.inference.id
  tags        = { Name = "cairns-trails-db-sg" }
}

# Access control has two independent layers (FR-016: not password-only) -
# this security group rule, and the Secrets Manager credential itself.
resource "aws_security_group_rule" "db_from_lambda" {
  type                     = "ingress"
  from_port                = 5432
  to_port                  = 5432
  protocol                 = "tcp"
  security_group_id        = aws_security_group.database.id
  source_security_group_id = aws_security_group.lambda.id
  description              = "Prediction worker Lambda to Postgres"
}

resource "aws_db_instance" "trails" {
  identifier        = "cairns-trails-db"
  engine            = "postgres"
  engine_version    = "16.13"
  instance_class    = "db.t3.micro"
  allocated_storage = 20
  db_name           = "cairns"
  username          = "cairns_app"
  password          = random_password.db.result

  db_subnet_group_name   = aws_db_subnet_group.trails.name
  vpc_security_group_ids = [aws_security_group.database.id]
  publicly_accessible    = false
  multi_az               = false
  storage_encrypted      = true

  # POC-friendly defaults so `terraform destroy` actually tears this down
  # during iteration - flip these once this holds real production data (see
  # aws/README.md).
  skip_final_snapshot = true
  deletion_protection = false
  apply_immediately   = true

  tags = { Name = "cairns-trails-db" }
}
