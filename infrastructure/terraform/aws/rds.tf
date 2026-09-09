# RDS PostgreSQL — the AWS equivalent of the superseded DigitalOcean
# Managed PostgreSQL cluster (database.tf). PostGIS is enabled the same
# way that module did it (a `postgresql_extension` resource against the
# `postgresql` provider, since RDS — like DigitalOcean Managed
# PostgreSQL — has no dedicated Terraform resource for enabling a
# database extension), not a new mechanism.

resource "aws_db_subnet_group" "postgres" {
  name       = "${var.project_name}-${var.environment}-pg-subnets"
  subnet_ids = aws_subnet.private[*].id

  tags = {
    Environment = var.environment
  }
}

resource "aws_security_group" "postgres" {
  name_prefix = "${var.project_name}-${var.environment}-pg-"
  description = "Allow Postgres access from EKS worker nodes only."
  vpc_id      = aws_vpc.vistaar.id

  ingress {
    description     = "Postgres from EKS nodes"
    from_port       = 5432
    to_port         = 5432
    protocol        = "tcp"
    security_groups = [aws_eks_cluster.vistaar.vpc_config[0].cluster_security_group_id]
  }

  egress {
    from_port   = 0
    to_port     = 0
    protocol    = "-1"
    cidr_blocks = ["0.0.0.0/0"]
  }

  tags = {
    Name = "${var.project_name}-${var.environment}-pg-sg"
  }

  lifecycle {
    create_before_destroy = true
  }
}

resource "aws_db_instance" "postgres" {
  identifier     = "${var.project_name}-${var.environment}-pg"
  engine         = "postgres"
  engine_version = var.postgres_version
  instance_class = var.postgres_instance_class

  allocated_storage     = var.postgres_allocated_storage_gb
  max_allocated_storage = var.postgres_allocated_storage_gb * 2
  storage_type          = "gp3"
  storage_encrypted     = true

  db_name  = "vistaar_db"
  username = "vistaar_admin"
  # RDS requires an explicit password at creation — Terraform will
  # prompt for/read this from TF_VAR_postgres_password (never commit a
  # real value). manage_master_user_password (AWS Secrets Manager-
  # generated, no Terraform-visible password at all) is the safer
  # alternative once a real AWS account exists — deliberately not
  # assumed here without confirming Secrets Manager is an approved
  # piece of the real deployment.
  password = var.postgres_password

  db_subnet_group_name   = aws_db_subnet_group.postgres.name
  vpc_security_group_ids = [aws_security_group.postgres.id]
  publicly_accessible    = false

  # Multi-AZ (owner decision, 2026-09-03, item 14 cost/capacity review:
  # "availability/redundancy requirements"). Was single-AZ, matching
  # the superseded DO module's own single-node Postgres cluster —
  # upgraded here because this is the one clear-cut recommendation a
  # cost/capacity review can make without load-test evidence:
  # automatic failover to a standby in a second AZ is standard practice
  # for a payments/ride-ledger database regardless of traffic volume,
  # unlike throughput sizing (instance class/count), which genuinely
  # depends on measured load this environment doesn't have yet (see
  # docs/03-architecture/aws-cost-capacity-review-2026-09-03.md — no
  # capacity claim is made there without real benchmark evidence).
  # Roughly doubles this line item's own cost — a real, named trade-off,
  # not a free upgrade.
  multi_az = true

  backup_retention_period = 7
  skip_final_snapshot     = false
  final_snapshot_identifier = "${var.project_name}-${var.environment}-pg-final"
  deletion_protection      = true

  tags = {
    Environment = var.environment
  }
}

# ADR-0010 Decision 4 / database-design.md §9.1: ride.rides requires
# GEOMETRY(Point, 4326) columns. RDS PostgreSQL supports PostGIS as an
# extension on every currently-supported major version — verify the
# specific var.postgres_version chosen still does before the first real
# apply.
resource "postgresql_extension" "postgis" {
  name     = "postgis"
  database = aws_db_instance.postgres.db_name

  depends_on = [aws_db_instance.postgres]
}
