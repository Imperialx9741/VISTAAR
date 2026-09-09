# --- Managed PostgreSQL ---

resource "digitalocean_database_cluster" "postgres" {
  name                 = "${var.project_name}-${var.environment}-pg"
  engine               = "pg"
  version              = var.postgres_version
  size                 = var.postgres_size
  region               = var.region
  node_count           = 1
  private_network_uuid = digitalocean_vpc.vistaar.id
}

resource "digitalocean_database_db" "vistaar_db" {
  cluster_id = digitalocean_database_cluster.postgres.id
  name       = "vistaar_db"
}

resource "digitalocean_database_firewall" "postgres" {
  cluster_id = digitalocean_database_cluster.postgres.id

  rule {
    type  = "k8s"
    value = digitalocean_kubernetes_cluster.vistaar.id
  }
}

# ADR-0010 Decision 4 / database-design.md §9.1: ride.rides requires
# GEOMETRY(Point, 4326) columns. DigitalOcean Managed PostgreSQL lists
# postgis among its supported extensions, but has no dedicated
# Terraform resource for enabling one — this uses the separate
# `postgresql` provider (configured in versions.tf against this same
# cluster) to run the equivalent of `CREATE EXTENSION postgis;`.
resource "postgresql_extension" "postgis" {
  name     = "postgis"
  database = digitalocean_database_db.vistaar_db.name

  depends_on = [digitalocean_database_firewall.postgres]
}

# --- Managed Redis ---

resource "digitalocean_database_cluster" "redis" {
  name = "${var.project_name}-${var.environment}-redis"
  # DigitalOcean's managed in-memory offering is Valkey-compatible
  # (protocol-compatible with the redis-py client this backend already
  # uses); the provider's engine slug remains "redis".
  engine               = "redis"
  version              = "7"
  size                 = var.redis_size
  region               = var.region
  node_count           = 1
  private_network_uuid = digitalocean_vpc.vistaar.id
}

resource "digitalocean_database_firewall" "redis" {
  cluster_id = digitalocean_database_cluster.redis.id

  rule {
    type  = "k8s"
    value = digitalocean_kubernetes_cluster.vistaar.id
  }
}
