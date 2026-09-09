# No DigitalOcean-managed Kafka product exists (ADR-0035 Decision 1) —
# a single always-on Droplet self-hosts the same apache/kafka:3.7.0
# KRaft-mode image already used in
# infrastructure/docker/docker-compose.dev.yml. Not highly available;
# replacing this with a real managed/clustered Kafka later only touches
# this file plus kubernetes/kafka-external-service.yaml, per ADR-0035's
# own consequence note — the application only ever talks to
# KAFKA_BOOTSTRAP_SERVERS.

resource "digitalocean_droplet" "kafka" {
  name     = "${var.project_name}-${var.environment}-kafka"
  region   = var.region
  size     = var.kafka_droplet_size
  image    = "ubuntu-22-04-x64"
  vpc_uuid = digitalocean_vpc.vistaar.id

  user_data = templatefile("${path.module}/kafka-cloud-init.yaml.tpl", {
    kafka_image = var.kafka_image
  })
}

resource "digitalocean_firewall" "kafka" {
  name        = "${var.project_name}-${var.environment}-kafka-fw"
  droplet_ids = [digitalocean_droplet.kafka.id]

  inbound_rule {
    protocol         = "tcp"
    port_range       = "9092"
    source_addresses = [digitalocean_vpc.vistaar.ip_range]
  }

  inbound_rule {
    protocol         = "tcp"
    port_range       = "22"
    source_addresses = ["0.0.0.0/0", "::/0"]
  }

  outbound_rule {
    protocol              = "tcp"
    port_range            = "1-65535"
    destination_addresses = ["0.0.0.0/0", "::/0"]
  }
}
