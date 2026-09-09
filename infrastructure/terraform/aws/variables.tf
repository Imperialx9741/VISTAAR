variable "project_name" {
  description = "Prefix applied to every AWS resource name/tag."
  type        = string
  default     = "vistaar"
}

variable "region" {
  description = "AWS region. ap-south-1 (Mumbai) is closest to VISTAAR's India-only user base — the same reasoning the superseded DigitalOcean module used for blr1 (ADR-0035/ADR-0063)."
  type        = string
  default     = "ap-south-1"
}

variable "environment" {
  description = "Deployment environment tag (e.g. production, staging)."
  type        = string
  default     = "production"
}

variable "vpc_cidr" {
  type    = string
  default = "10.20.0.0/16"
}

variable "availability_zones" {
  description = "At least 2 required — EKS and RDS Multi-AZ both need subnets in more than one AZ. ap-south-1a/1b are Mumbai's first two."
  type        = list(string)
  default     = ["ap-south-1a", "ap-south-1b"]
}

# --- EKS ---

variable "kubernetes_version" {
  description = "EKS Kubernetes version. Pinned explicitly (unlike the superseded DOKS module's \"latest\") — EKS has no floating \"latest\" concept; an unset version defaults to whatever the aws provider itself currently defaults to, which is not a decision this file should make implicitly. Review against the current EKS-supported version list before the first real apply."
  type        = string
  default     = "1.30"
}

variable "node_instance_type" {
  description = "EC2 instance type for the default EKS managed node group. m6i.large (2 vCPU / 8GB) is a reasonable starting point matching the superseded DOKS module's s-2vcpu-4gb sizing in vCPU count, not a cost/capacity decision this file makes on your behalf."
  type        = string
  default     = "m6i.large"
}

variable "node_count_min" {
  type    = number
  default = 2
}

variable "node_count_max" {
  type    = number
  default = 5
}

# --- RDS PostgreSQL ---

variable "postgres_instance_class" {
  type    = string
  default = "db.m6i.large"
}

variable "postgres_version" {
  description = "Must be an RDS-supported PostgreSQL version with PostGIS available in its extension list (all currently-supported RDS Postgres major versions include PostGIS) — verify against the current RDS PostgreSQL release notes before the first real apply."
  type    = string
  default = "16.4"
}

variable "postgres_allocated_storage_gb" {
  type    = number
  default = 100
}

variable "postgres_password" {
  description = "Master password for the RDS PostgreSQL instance. No default on purpose — supply via TF_VAR_postgres_password or a .tfvars file that is never committed. Never hardcode a real value in this repo."
  type        = string
  sensitive   = true
}

# --- ElastiCache (Redis) ---

variable "redis_node_type" {
  type    = string
  default = "cache.m6g.large"
}

variable "redis_engine_version" {
  type    = string
  default = "7.1"
}

# --- Kafka EC2 host (no fully-managed MSK cluster provisioned here —
# see ADR-0063 §3 for why, and README.md for the MSK alternative) ---

variable "kafka_instance_type" {
  type    = string
  default = "m6i.large"
}

variable "kafka_ami_id" {
  description = "An Ubuntu 22.04 LTS AMI id for ap-south-1 — AMI ids are region- and publish-date-specific and change over time; look up the current canonical Ubuntu 22.04 AMI for the target region (e.g. via `aws ec2 describe-images --owners 099720109477 ...`) before the first real apply. Left unset (empty string fails validate on purpose) rather than a guessed, possibly-stale id."
  type        = string
  default     = ""
}

variable "kafka_image" {
  description = "The same apache/kafka image tag already used in infrastructure/docker/docker-compose.dev.yml, run via Docker on a plain EC2 instance through user-data — matches the superseded DigitalOcean module's own Droplet approach exactly."
  type        = string
  default     = "apache/kafka:3.7.0"
}

# --- S3 (object storage) ---

variable "storage_bucket_name" {
  description = "Must be globally unique across all of AWS S3 — the default below will very likely collide with an existing bucket; set a real, unique name before the first apply."
  type        = string
  default     = "vistaar-storage"
}

# --- ECR (container registry) ---

variable "backend_ecr_repository_name" {
  type    = string
  default = "vistaar-backend"
}
