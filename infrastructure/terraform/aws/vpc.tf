# AWS has no single-resource VPC equivalent to the superseded
# DigitalOcean module's `digitalocean_vpc` — EKS, RDS, ElastiCache, and
# the Kafka EC2 host all need explicit subnets in more than one
# Availability Zone (EKS/RDS Multi-AZ requirements), plus route tables
# and a NAT Gateway for private-subnet egress (package installs, pulling
# container images, etc.). This is a real increase in Terraform surface
# versus the DO module, not an oversight — AWS's networking model is
# simply more explicit.
#
# Layout: one VPC, one public subnet + one private subnet per AZ. EKS
# nodes, RDS, ElastiCache, and the Kafka EC2 host all live in the
# private subnets — nothing except the ALB (via the ingress controller,
# provisioned by Kubernetes itself, not this Terraform) and the NAT
# Gateway sit in the public ones.
#
# Single NAT Gateway (not one per AZ) — a reasonable starting point
# matching the superseded DO module's own "single-node, not highly
# available" choices (e.g. single Kafka Droplet, single-node Postgres),
# not a cost/capacity decision this file makes on the owner's behalf. A
# NAT Gateway per AZ is the standard upgrade once real availability
# requirements are set.

resource "aws_vpc" "vistaar" {
  cidr_block           = var.vpc_cidr
  enable_dns_support   = true
  enable_dns_hostnames = true

  tags = {
    Name        = "${var.project_name}-${var.environment}-vpc"
    Environment = var.environment
  }
}

resource "aws_internet_gateway" "vistaar" {
  vpc_id = aws_vpc.vistaar.id

  tags = {
    Name = "${var.project_name}-${var.environment}-igw"
  }
}

resource "aws_subnet" "public" {
  count                   = length(var.availability_zones)
  vpc_id                  = aws_vpc.vistaar.id
  cidr_block              = cidrsubnet(var.vpc_cidr, 8, count.index)
  availability_zone       = var.availability_zones[count.index]
  map_public_ip_on_launch = true

  tags = {
    Name = "${var.project_name}-${var.environment}-public-${var.availability_zones[count.index]}"
    # Required by the AWS Load Balancer Controller / in-tree ELB
    # provisioner to auto-discover subnets for internet-facing
    # LoadBalancer Services and Ingresses.
    "kubernetes.io/role/elb"                                       = "1"
    "kubernetes.io/cluster/${var.project_name}-${var.environment}" = "shared"
  }
}

resource "aws_subnet" "private" {
  count             = length(var.availability_zones)
  vpc_id            = aws_vpc.vistaar.id
  cidr_block        = cidrsubnet(var.vpc_cidr, 8, count.index + 100)
  availability_zone = var.availability_zones[count.index]

  tags = {
    Name = "${var.project_name}-${var.environment}-private-${var.availability_zones[count.index]}"
    # Same discovery tag as the public subnets, for internal
    # LoadBalancer Services / the EKS control plane's own use.
    "kubernetes.io/role/internal-elb"                              = "1"
    "kubernetes.io/cluster/${var.project_name}-${var.environment}" = "shared"
  }
}

resource "aws_eip" "nat" {
  domain = "vpc"

  tags = {
    Name = "${var.project_name}-${var.environment}-nat-eip"
  }
}

resource "aws_nat_gateway" "vistaar" {
  allocation_id = aws_eip.nat.id
  # A single NAT Gateway in the first public subnet — see this file's
  # own header comment for why this isn't one per AZ.
  subnet_id = aws_subnet.public[0].id

  tags = {
    Name = "${var.project_name}-${var.environment}-nat"
  }

  depends_on = [aws_internet_gateway.vistaar]
}

resource "aws_route_table" "public" {
  vpc_id = aws_vpc.vistaar.id

  route {
    cidr_block = "0.0.0.0/0"
    gateway_id = aws_internet_gateway.vistaar.id
  }

  tags = {
    Name = "${var.project_name}-${var.environment}-public-rt"
  }
}

resource "aws_route_table" "private" {
  vpc_id = aws_vpc.vistaar.id

  route {
    cidr_block     = "0.0.0.0/0"
    nat_gateway_id = aws_nat_gateway.vistaar.id
  }

  tags = {
    Name = "${var.project_name}-${var.environment}-private-rt"
  }
}

resource "aws_route_table_association" "public" {
  count          = length(aws_subnet.public)
  subnet_id      = aws_subnet.public[count.index].id
  route_table_id = aws_route_table.public.id
}

resource "aws_route_table_association" "private" {
  count          = length(aws_subnet.private)
  subnet_id      = aws_subnet.private[count.index].id
  route_table_id = aws_route_table.private.id
}
