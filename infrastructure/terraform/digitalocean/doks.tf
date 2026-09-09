resource "digitalocean_kubernetes_cluster" "vistaar" {
  name     = "${var.project_name}-${var.environment}"
  region   = var.region
  version  = var.kubernetes_version
  vpc_uuid = digitalocean_vpc.vistaar.id

  node_pool {
    name       = "${var.project_name}-default-pool"
    size       = var.node_size
    auto_scale = true
    min_nodes  = var.node_count_min
    max_nodes  = var.node_count_max
    tags       = ["vistaar", var.environment]
  }
}
