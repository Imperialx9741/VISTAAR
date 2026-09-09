output "state_bucket_name" {
  value = aws_s3_bucket.terraform_state.id
}

output "lock_table_name" {
  value = aws_dynamodb_table.terraform_lock.name
}

output "backend_config_snippet" {
  description = "Copy into ../aws/backend.hcl (see that directory's README) to point the main module at this remote state."
  value       = <<-EOT
    bucket         = "${aws_s3_bucket.terraform_state.id}"
    key            = "vistaar/aws/terraform.tfstate"
    region         = "${var.region}"
    dynamodb_table = "${aws_dynamodb_table.terraform_lock.name}"
    encrypt        = true
  EOT
}
