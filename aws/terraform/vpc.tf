# Three-tier VPC, mirroring aws/cdk/lib/inference-stack.ts's ec2.Vpc:
# public (holds the NAT Gateway), lambda-private (the worker - needs
# outbound internet for Open-Meteo, which has no VPC endpoint), and
# database-isolated (the RDS instance - no route out at all). See
# aws/SYSTEM_DESIGN.md section 6.5 for why this shape exists.

data "aws_availability_zones" "available" {
  state = "available"
}

locals {
  azs = slice(data.aws_availability_zones.available.names, 0, 2)
}

resource "aws_vpc" "inference" {
  cidr_block           = "10.0.0.0/16"
  enable_dns_hostnames = true
  enable_dns_support   = true
  tags                 = { Name = "cairns-inference-vpc" }
}

resource "aws_internet_gateway" "igw" {
  vpc_id = aws_vpc.inference.id
  tags   = { Name = "cairns-inference-igw" }
}

resource "aws_subnet" "public" {
  count                   = 2
  vpc_id                  = aws_vpc.inference.id
  cidr_block              = "10.0.${count.index}.0/24"
  availability_zone       = local.azs[count.index]
  map_public_ip_on_launch = true
  tags                    = { Name = "cairns-public-${count.index}" }
}

resource "aws_subnet" "lambda_private" {
  count             = 2
  vpc_id            = aws_vpc.inference.id
  cidr_block        = "10.0.${count.index + 2}.0/24"
  availability_zone = local.azs[count.index]
  tags              = { Name = "cairns-lambda-private-${count.index}" }
}

resource "aws_subnet" "database_isolated" {
  count             = 2
  vpc_id            = aws_vpc.inference.id
  cidr_block        = "10.0.${count.index + 4}.0/24"
  availability_zone = local.azs[count.index]
  tags              = { Name = "cairns-database-isolated-${count.index}" }
}

# One NAT Gateway, not one per AZ, to keep the standing cost down - matches
# the CDK stack's natGateways: 1 (see aws/README.md's cost note).
resource "aws_eip" "nat" {
  domain = "vpc"
  tags   = { Name = "cairns-nat-eip" }
}

resource "aws_nat_gateway" "nat" {
  allocation_id = aws_eip.nat.id
  subnet_id     = aws_subnet.public[0].id
  tags          = { Name = "cairns-nat" }
  depends_on    = [aws_internet_gateway.igw]
}

resource "aws_route_table" "public" {
  vpc_id = aws_vpc.inference.id
  route {
    cidr_block = "0.0.0.0/0"
    gateway_id = aws_internet_gateway.igw.id
  }
  tags = { Name = "cairns-public-rt" }
}

resource "aws_route_table_association" "public" {
  count          = 2
  subnet_id      = aws_subnet.public[count.index].id
  route_table_id = aws_route_table.public.id
}

resource "aws_route_table" "lambda_private" {
  vpc_id = aws_vpc.inference.id
  route {
    cidr_block     = "0.0.0.0/0"
    nat_gateway_id = aws_nat_gateway.nat.id
  }
  tags = { Name = "cairns-lambda-private-rt" }
}

resource "aws_route_table_association" "lambda_private" {
  count          = 2
  subnet_id      = aws_subnet.lambda_private[count.index].id
  route_table_id = aws_route_table.lambda_private.id
}

# database-isolated subnets deliberately get no 0.0.0.0/0 route at all -
# matches CDK's PRIVATE_ISOLATED subnet type (FR-016: not reachable from the
# open internet).
resource "aws_route_table" "database_isolated" {
  vpc_id = aws_vpc.inference.id
  tags   = { Name = "cairns-database-isolated-rt" }
}

resource "aws_route_table_association" "database_isolated" {
  count          = 2
  subnet_id      = aws_subnet.database_isolated[count.index].id
  route_table_id = aws_route_table.database_isolated.id
}

# Free gateway endpoints so S3/DynamoDB traffic from the Lambda's subnet
# skips the NAT Gateway - Open-Meteo (an arbitrary external host) still
# needs the NAT Gateway; no endpoint type covers "the general internet."
resource "aws_vpc_endpoint" "s3" {
  vpc_id            = aws_vpc.inference.id
  service_name      = "com.amazonaws.${var.aws_region}.s3"
  vpc_endpoint_type = "Gateway"
  route_table_ids   = [aws_route_table.lambda_private.id, aws_route_table.database_isolated.id]
  tags              = { Name = "cairns-s3-endpoint" }
}

resource "aws_vpc_endpoint" "dynamodb" {
  vpc_id            = aws_vpc.inference.id
  service_name      = "com.amazonaws.${var.aws_region}.dynamodb"
  vpc_endpoint_type = "Gateway"
  route_table_ids   = [aws_route_table.lambda_private.id]
  tags              = { Name = "cairns-dynamodb-endpoint" }
}
