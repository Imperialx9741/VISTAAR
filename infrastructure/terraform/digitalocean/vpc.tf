# All resources (DOKS, Managed PostgreSQL, Managed Redis, the Kafka
# Droplet) share one VPC so they can reach each other over private
# networking without transiting the public internet.
resource "digitalocean_vpc" "vistaar" {
  name     = "${var.project_name}-${var.environment}-vpc"
  region   = var.region
  ip_range = "10.10.0.0/16"
}
