terraform {
  required_version = ">= 1.7.0"

  # Remote state (added 2026-09-03, closing deployment-runbook.md §5.3's
  # previously-open "local state only" gap). A `backend "s3"` block
  # cannot reference variables — Terraform requires backend config to be
  # static or supplied at `terraform init` time — so this is left
  # deliberately empty and filled in via `-backend-config=backend.hcl`
  # (see backend.hcl.example and this directory's README). The bucket
  # and lock table it points at are provisioned by the separate
  # ../aws-state-backend/ module, not by this one — a Terraform backend
  # can't bootstrap its own storage.
  backend "s3" {}

  required_providers {
    aws = {
      source  = "hashicorp/aws"
      version = "~> 5.60"
    }
    # Used only to run `CREATE EXTENSION postgis;` against the RDS
    # PostgreSQL instance once it exists — the aws provider has no
    # resource for enabling a database extension (mirrors the same
    # pattern the superseded DigitalOcean module used, ADR-0035 §2).
    postgresql = {
      source  = "cyrilgdn/postgresql"
      version = "~> 1.21"
    }
    # Used only to fetch the EKS OIDC issuer's real certificate
    # thumbprint for aws_iam_openid_connect_provider (eks.tf) — the
    # standard, self-updating Terraform pattern (vs. hardcoding a
    # thumbprint that goes stale if AWS ever rotates the signing CA).
    tls = {
      source  = "hashicorp/tls"
      version = "~> 4.0"
    }
  }
}

provider "aws" {
  region = var.region
  # Reads AWS credentials from the environment (AWS_ACCESS_KEY_ID/
  # AWS_SECRET_ACCESS_KEY/AWS_SESSION_TOKEN) or a configured AWS CLI
  # profile — never hardcode credentials in this repo. See README.md in
  # this directory.
}

provider "postgresql" {
  host            = aws_db_instance.postgres.address
  port            = aws_db_instance.postgres.port
  username        = aws_db_instance.postgres.username
  password        = aws_db_instance.postgres.password
  database        = aws_db_instance.postgres.db_name
  sslmode         = "require"
  superuser       = false
  connect_timeout = 15
}
