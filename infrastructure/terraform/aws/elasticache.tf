# ElastiCache for Redis — the AWS equivalent of the superseded
# DigitalOcean Managed Redis (Valkey-compatible) cluster.

resource "aws_elasticache_subnet_group" "redis" {
  name       = "${var.project_name}-${var.environment}-redis-subnets"
  subnet_ids = aws_subnet.private[*].id
}

resource "aws_security_group" "redis" {
  name_prefix = "${var.project_name}-${var.environment}-redis-"
  description = "Allow Redis access from EKS worker nodes only."
  vpc_id      = aws_vpc.vistaar.id

  ingress {
    description     = "Redis from EKS nodes"
    from_port       = 6379
    to_port         = 6379
    protocol        = "tcp"
    security_groups = [aws_eks_cluster.vistaar.vpc_config[0].cluster_security_group_id]
  }

  egress {
    from_port   = 0
    to_port     = 0
    protocol    = "-1"
    cidr_blocks = ["0.0.0.0/0"]
  }

  tags = {
    Name = "${var.project_name}-${var.environment}-redis-sg"
  }

  lifecycle {
    create_before_destroy = true
  }
}

resource "aws_elasticache_replication_group" "redis" {
  replication_group_id = "${var.project_name}-${var.environment}-redis"
  description           = "VISTAAR rate-limiting/matching/session cache (security.md §83 — never the source of truth for anything financial)."

  engine         = "redis"
  engine_version = var.redis_engine_version
  node_type      = var.redis_node_type

  # A replica + automatic failover (owner decision, 2026-09-03, item 14
  # cost/capacity review). Was a single node, no failover, matching the
  # superseded DO module's own single-node Redis cluster — upgraded for
  # the same reason as rds.tf's multi_az above: this is a clear-cut
  # availability recommendation independent of traffic volume, not a
  # throughput/sizing guess. Redis is never the source of truth for
  # anything financial (security.md §83) — a failed node loses no
  # authoritative data — but it IS the real-time matching/rate-limiting
  # store, so a node failure with no replica would still degrade live
  # ride matching for however long recovery takes; a second node in a
  # different AZ with automatic failover removes that single point of
  # failure. Roughly doubles this line item's own cost.
  num_cache_clusters         = 2
  automatic_failover_enabled = true

  subnet_group_name = aws_elasticache_subnet_group.redis.name
  security_group_ids = [aws_security_group.redis.id]

  # TLS in transit — security.md §18's "production traffic must use
  # TLS" applies just as much to the backend-to-Redis hop as to the
  # public API; the app already connects with `rediss://` when this is
  # enabled (core/redis.py reads REDIS_URL as given, no code change
  # needed here).
  transit_encryption_enabled = true
  at_rest_encryption_enabled = true

  tags = {
    Environment = var.environment
  }
}
