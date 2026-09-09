output "kubernetes_cluster_id" {
  value = digitalocean_kubernetes_cluster.vistaar.id
}

output "kubeconfig_command" {
  description = "Run this to fetch kubeconfig for kubectl/helm access."
  value       = "doctl kubernetes cluster kubeconfig save ${digitalocean_kubernetes_cluster.vistaar.name}"
}

output "database_url" {
  description = "Feed into infrastructure/kubernetes/backend-secret.yaml's DATABASE_URL."
  value       = "postgresql://${digitalocean_database_cluster.postgres.user}:${digitalocean_database_cluster.postgres.password}@${digitalocean_database_cluster.postgres.private_host}:${digitalocean_database_cluster.postgres.port}/${digitalocean_database_db.vistaar_db.name}?sslmode=require"
  sensitive   = true
}

output "redis_url" {
  description = "Feed into infrastructure/kubernetes/backend-secret.yaml's REDIS_URL."
  value       = "rediss://default:${digitalocean_database_cluster.redis.password}@${digitalocean_database_cluster.redis.private_host}:${digitalocean_database_cluster.redis.port}/0"
  sensitive   = true
}

output "spaces_bucket_endpoint" {
  description = "Feed into backend-secret.yaml's STORAGE_ENDPOINT."
  value       = "https://${var.region}.digitaloceanspaces.com"
}

output "spaces_access_key" {
  value     = digitalocean_spaces_key.vistaar_storage.access_key
  sensitive = true
}

output "spaces_secret_key" {
  value     = digitalocean_spaces_key.vistaar_storage.secret_key
  sensitive = true
}

output "kafka_droplet_private_ip" {
  description = "Feed into infrastructure/kubernetes/kafka-external-service.yaml's REPLACE_ME_KAFKA_DROPLET_IP."
  value       = digitalocean_droplet.kafka.ipv4_address_private
}
