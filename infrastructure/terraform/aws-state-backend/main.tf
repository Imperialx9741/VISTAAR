# Bootstrap module — provisions the S3 bucket + DynamoDB lock table that
# ../aws/'s own remote state backend needs (deployment-runbook.md §5.3,
# previously an open gap: "local state only exists today"). This module
# is intentionally separate from ../aws/ and intentionally still uses
# *local* state itself — a Terraform remote-state backend cannot
# bootstrap its own storage; something has to create the bucket first,
# and that something's own state has nowhere remote to live yet. This is
# the standard, documented pattern for this exact chicken-and-egg
# problem (see README.md's own note), not an oversight.
#
# Apply this module ONCE, before the first `terraform init` of ../aws/
# with a backend block configured. After that, this module's own state
# file (kept locally, or manually moved somewhere durable — e.g. checked
# into a private ops repo, not this one) is rarely touched again.

terraform {
  required_version = ">= 1.7.0"

  required_providers {
    aws = {
      source  = "hashicorp/aws"
      version = "~> 5.60"
    }
  }
}

provider "aws" {
  region = var.region
}

# Owner decision, 2026-09-03: "Use an account-specific bucket naming
# convention: vistaar-terraform-state-<AWS_ACCOUNT_ID>-ap-south-1. Do
# not assume availability of a generic bucket name." Computed here from
# the real, currently-authenticated account — not typed in by hand, so
# it can never drift from the account actually being applied against.
# S3 bucket names are still globally unique across ALL AWS accounts
# (not just this one), so embedding the account ID makes a collision
# extremely unlikely but not a mathematical guarantee — "verify before
# creating it" in practice means: read the computed name in `terraform
# plan`'s output (it's a locals value, not hidden inside a resource)
# before running `apply`, and optionally `aws s3api head-bucket
# --bucket <name>` first to confirm directly.
data "aws_caller_identity" "current" {}

locals {
  state_bucket_name = "vistaar-terraform-state-${data.aws_caller_identity.current.account_id}-${var.region}"
}

resource "aws_s3_bucket" "terraform_state" {
  bucket = local.state_bucket_name

  # No `force_destroy` — accidentally deleting the bucket that holds the
  # main module's state would be catastrophic (loses Terraform's record
  # of every AWS resource it manages); require an explicit, deliberate
  # empty-then-delete instead of a one-flag `terraform destroy`.
  lifecycle {
    prevent_destroy = true
  }
}

resource "aws_s3_bucket_versioning" "terraform_state" {
  bucket = aws_s3_bucket.terraform_state.id
  versioning_configuration {
    status = "Enabled"
  }
}

resource "aws_s3_bucket_server_side_encryption_configuration" "terraform_state" {
  bucket = aws_s3_bucket.terraform_state.id
  rule {
    apply_server_side_encryption_by_default {
      sse_algorithm = "AES256"
    }
  }
}

resource "aws_s3_bucket_public_access_block" "terraform_state" {
  bucket                  = aws_s3_bucket.terraform_state.id
  block_public_acls       = true
  block_public_policy     = true
  ignore_public_acls      = true
  restrict_public_buckets = true
}

resource "aws_dynamodb_table" "terraform_lock" {
  name         = var.lock_table_name
  billing_mode = "PAY_PER_REQUEST"
  hash_key     = "LockID"

  attribute {
    name = "LockID"
    type = "S"
  }
}
