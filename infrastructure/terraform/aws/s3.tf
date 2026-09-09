# S3 — the AWS equivalent of the superseded DigitalOcean Spaces bucket.
# shared/storage.py's S3ObjectStorage (ADR-0031) was already built
# directly against boto3's S3 client with a configurable
# STORAGE_ENDPOINT — Spaces only ever needed that because it's an
# S3-compatible *third-party* store (ADR-0035 §3). Moving to AWS is
# actually a simplification: STORAGE_ENDPOINT is left blank in the real
# Kubernetes Secret (boto3's own default AWS endpoint resolution), and
# no application code changes at all.

resource "aws_s3_bucket" "vistaar_storage" {
  bucket = var.storage_bucket_name

  tags = {
    Environment = var.environment
  }
}

resource "aws_s3_bucket_public_access_block" "vistaar_storage" {
  bucket = aws_s3_bucket.vistaar_storage.id

  block_public_acls       = true
  block_public_policy     = true
  ignore_public_acls      = true
  restrict_public_buckets = true
}

resource "aws_s3_bucket_versioning" "vistaar_storage" {
  bucket = aws_s3_bucket.vistaar_storage.id

  versioning_configuration {
    status = "Enabled"
  }
}

resource "aws_s3_bucket_server_side_encryption_configuration" "vistaar_storage" {
  bucket = aws_s3_bucket.vistaar_storage.id

  rule {
    apply_server_side_encryption_by_default {
      sse_algorithm = "AES256"
    }
  }
}

# A dedicated IAM user + access key scoped to only this bucket, rather
# than reusing the credentials Terraform/kubectl themselves run as —
# mirrors the superseded DigitalOcean module's own dedicated Spaces key
# exactly (digitalocean_spaces_key), and needs no change to
# shared/storage.py or the Kubernetes Secret shape it reads from
# (STORAGE_ACCESS_KEY/STORAGE_SECRET_KEY).
#
# The more AWS-native alternative — IAM Roles for Service Accounts
# (IRSA), no static credentials in the cluster at all — is the
# recommended upgrade once the EKS cluster's OIDC provider is set up and
# the backend's Kubernetes ServiceAccount is annotated for it; not done
# here, since it also requires a coordinated change to
# infrastructure/kubernetes/ this module alone can't make, and this
# starting point already works with zero application/manifest changes.
resource "aws_iam_user" "storage" {
  name = "${var.project_name}-${var.environment}-storage"
}

resource "aws_iam_user_policy" "storage" {
  name = "${var.project_name}-${var.environment}-storage-rw"
  user = aws_iam_user.storage.name

  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [{
      Effect = "Allow"
      Action = [
        "s3:GetObject",
        "s3:PutObject",
        "s3:DeleteObject",
        "s3:ListBucket",
      ]
      Resource = [
        aws_s3_bucket.vistaar_storage.arn,
        "${aws_s3_bucket.vistaar_storage.arn}/*",
      ]
    }]
  })
}

resource "aws_iam_access_key" "storage" {
  user = aws_iam_user.storage.name
}
