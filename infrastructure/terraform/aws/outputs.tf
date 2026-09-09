output "eks_cluster_name" {
  value = aws_eks_cluster.vistaar.name
}

output "kubeconfig_command" {
  description = "Run this to fetch kubeconfig for kubectl/helm access."
  value       = "aws eks update-kubeconfig --region ${var.region} --name ${aws_eks_cluster.vistaar.name}"
}

output "ecr_repository_url" {
  description = "Feed into .github/workflows/deploy-aws.yml's registry target and infrastructure/kubernetes/backend-deployment.yaml's image reference."
  value       = aws_ecr_repository.backend.repository_url
}

output "database_url" {
  description = "Feed into infrastructure/kubernetes/backend-secret.yaml's DATABASE_URL."
  value       = "postgresql://${aws_db_instance.postgres.username}:${var.postgres_password}@${aws_db_instance.postgres.address}:${aws_db_instance.postgres.port}/${aws_db_instance.postgres.db_name}?sslmode=require"
  sensitive   = true
}

output "redis_url" {
  description = "Feed into infrastructure/kubernetes/backend-secret.yaml's REDIS_URL."
  value       = "rediss://${aws_elasticache_replication_group.redis.primary_endpoint_address}:6379/0"
  sensitive   = true
}

output "storage_bucket_name" {
  description = "Feed into backend-secret.yaml's STORAGE_BUCKET."
  value       = aws_s3_bucket.vistaar_storage.id
}

output "storage_region" {
  description = "Feed into backend-secret.yaml's STORAGE_REGION. STORAGE_ENDPOINT should be left blank — real AWS S3, not a third-party S3-compatible store, so boto3's own default endpoint resolution applies."
  value       = var.region
}

output "storage_access_key" {
  value     = aws_iam_access_key.storage.id
  sensitive = true
}

output "storage_secret_key" {
  value     = aws_iam_access_key.storage.secret
  sensitive = true
}

output "kafka_instance_private_ip" {
  description = "Feed into infrastructure/kubernetes/kafka-external-service.yaml's REPLACE_ME_KAFKA_DROPLET_IP (rename that placeholder when this module replaces the DigitalOcean one)."
  value       = aws_instance.kafka.private_ip
}

output "aws_load_balancer_controller_role_arn" {
  description = "Feed into the eks.k8s.aws/role-arn annotation on the aws-load-balancer-controller ServiceAccount when installing the Helm chart — see infrastructure/kubernetes/README.md's exact steps."
  value       = aws_iam_role.aws_load_balancer_controller.arn
}
