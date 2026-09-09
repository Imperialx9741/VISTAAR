variable "project_name" {
  description = "Prefix applied to every DigitalOcean resource name."
  type        = string
  default     = "vistaar"
}

variable "region" {
  description = "DigitalOcean region slug. blr1 (Bangalore) is closest to VISTAAR's India-only user base."
  type        = string
  default     = "blr1"
}

variable "environment" {
  description = "Deployment environment tag (e.g. production, staging)."
  type        = string
  default     = "production"
}

# --- DOKS ---

variable "kubernetes_version" {
  description = "DOKS Kubernetes version slug. Leave unset to pin explicitly once a real cluster is planned; \"latest\" auto-selects DigitalOcean's current default at apply time, which can change between applies."
  type        = string
  default     = "latest"
}

variable "node_size" {
  description = "Droplet size slug for the default DOKS node pool."
  type        = string
  default     = "s-2vcpu-4gb"
}

variable "node_count_min" {
  type    = number
  default = 2
}

variable "node_count_max" {
  type    = number
  default = 5
}

# --- Managed PostgreSQL ---

variable "postgres_size" {
  description = "DigitalOcean Managed PostgreSQL plan slug."
  type        = string
  default     = "db-s-2vcpu-4gb"
}

variable "postgres_version" {
  type    = string
  default = "16"
}

# --- Managed Redis (Valkey) ---

variable "redis_size" {
  description = "DigitalOcean Managed Redis (Valkey-compatible) plan slug."
  type        = string
  default     = "db-s-1vcpu-1gb"
}

# --- Kafka Droplet (no DigitalOcean-managed Kafka product exists —
# ADR-0035 Decision 1) ---

variable "kafka_droplet_size" {
  type    = string
  default = "s-2vcpu-4gb"
}

variable "kafka_image" {
  description = "The same apache/kafka image tag already used in infrastructure/docker/docker-compose.dev.yml, run via Docker on a plain Droplet through cloud-init."
  type        = string
  default     = "apache/kafka:3.7.0"
}

# --- Spaces (S3-compatible object storage) ---

variable "spaces_bucket_name" {
  type    = string
  default = "vistaar-storage"
}
