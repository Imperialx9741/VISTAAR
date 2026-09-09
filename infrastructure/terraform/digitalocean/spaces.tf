# DigitalOcean Spaces — S3-compatible object storage. ADR-0035 Decision
# 2: shared/storage.py's S3ObjectStorage (built under ADR-0031) already
# supports a configurable STORAGE_ENDPOINT, so no application code
# changes for this move — only these Terraform-provisioned values feed
# into backend-secret.yaml's STORAGE_ENDPOINT/STORAGE_ACCESS_KEY/
# STORAGE_SECRET_KEY.
resource "digitalocean_spaces_bucket" "vistaar_storage" {
  name   = var.spaces_bucket_name
  region = var.region
  acl    = "private"
}

# A dedicated Spaces access key scoped to this bucket, rather than
# reusing the DIGITALOCEAN_TOKEN used to run Terraform/kubectl itself.
resource "digitalocean_spaces_key" "vistaar_storage" {
  name = "${var.project_name}-${var.environment}-storage"

  grant {
    bucket     = digitalocean_spaces_bucket.vistaar_storage.name
    permission = "readwrite"
  }
}
