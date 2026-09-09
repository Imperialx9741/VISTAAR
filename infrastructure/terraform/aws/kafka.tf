# No fully-managed Kafka is provisioned here — a single always-on EC2
# instance self-hosts the same apache/kafka:3.7.0 KRaft-mode image
# already used in infrastructure/docker/docker-compose.dev.yml, exactly
# mirroring the superseded DigitalOcean module's own single-Droplet
# approach (ADR-0035 Decision 1) rather than assuming AWS MSK (a real,
# genuinely-managed alternative AWS offers that DigitalOcean didn't —
# see ADR-0063 §3 for why this file doesn't default to it and how to
# switch). Not highly available; replacing this with MSK later only
# touches this file plus kubernetes/kafka-external-service.yaml — the
# application only ever talks to KAFKA_BOOTSTRAP_SERVERS.

resource "aws_security_group" "kafka" {
  name_prefix = "${var.project_name}-${var.environment}-kafka-"
  description = "Kafka broker access from EKS worker nodes; SSH from anywhere (tighten before real production use)."
  vpc_id      = aws_vpc.vistaar.id

  ingress {
    description     = "Kafka from EKS nodes"
    from_port       = 9092
    to_port         = 9092
    protocol        = "tcp"
    security_groups = [aws_eks_cluster.vistaar.vpc_config[0].cluster_security_group_id]
  }

  ingress {
    description = "SSH — same open-to-internet default the superseded DO module's firewall used; restrict to a known operator CIDR/bastion before real production use."
    from_port   = 22
    to_port     = 22
    protocol    = "tcp"
    cidr_blocks = ["0.0.0.0/0"]
  }

  egress {
    from_port   = 0
    to_port     = 0
    protocol    = "-1"
    cidr_blocks = ["0.0.0.0/0"]
  }

  tags = {
    Name = "${var.project_name}-${var.environment}-kafka-sg"
  }

  lifecycle {
    create_before_destroy = true
  }
}

resource "aws_instance" "kafka" {
  ami                    = var.kafka_ami_id
  instance_type          = var.kafka_instance_type
  subnet_id              = aws_subnet.private[0].id
  vpc_security_group_ids = [aws_security_group.kafka.id]

  user_data = templatefile("${path.module}/kafka-user-data.yaml.tpl", {
    kafka_image = var.kafka_image
  })

  root_block_device {
    volume_size = 50
    volume_type = "gp3"
    encrypted   = true
  }

  tags = {
    Name        = "${var.project_name}-${var.environment}-kafka"
    Environment = var.environment
  }
}
