# Local Development Infrastructure

This directory contains the Docker Compose configuration to spin up the local infrastructure foundation for **VISTAAR** development.

> [!IMPORTANT]
> This infrastructure is configured **strictly for local development**. It exposes services locally with credentials matching those in the workspace's `.env.example` file.
> Application integration (database models, clients, business logic) is not implemented yet and will be added in later tasks.

## Services Included

The stack comprises the following local services:

1. **PostgreSQL** (`postgres:16-alpine`): Exposed on host port `5432`.
2. **Redis** (`redis:7-alpine`): Exposed on host port `6379`.
3. **Kafka** (`apache/kafka:3.7.0`): Single-node broker running in **KRaft** mode (no ZooKeeper required). Exposed on host port `9092`.
4. **Prometheus** (`prom/prometheus:v2.53.0`, ADR-0053): Scrapes the backend's own `GET /metrics` (run via `uvicorn` on the host, reached through `host.docker.internal`). Exposed on host port `9090`.
5. **Grafana** (`grafana/grafana:11.1.0`, ADR-0053): Dashboards over Prometheus, with a starter "VISTAAR Backend" dashboard auto-provisioned. Exposed on host port `3001`. Default local-dev-only credentials: `admin` / `admin`.

## Prerequisites

- **Docker** (version 20.10+ recommended)
- **Docker Compose** (V2 recommended)

## Network Configuration

All services communicate internally within a dedicated bridge network named `vistaar_dev_network`. Services can reach each other using their service names (`postgres`, `redis`, `kafka`).

## Ports and Exposed Services

| Service | Host Port | Internal Port | Protocol | Usage / Credential Match |
| :--- | :--- | :--- | :--- | :--- |
| **PostgreSQL** | `5433` | `5432` | TCP | Match `DATABASE_URL=postgresql://db_user:db_password@127.0.0.1:5433/vistaar_db` (Port 5433 avoids conflict with native Windows PostgreSQL service) |
| **Redis** | `6379` | `6379` | TCP | Match `REDIS_URL=redis://127.0.0.1:6379/0` |
| **Kafka** | `9092` | `9092` | TCP | Match `KAFKA_BOOTSTRAP_SERVERS=127.0.0.1:9092` |
| **Prometheus** | `9090` | `9090` | HTTP | `http://localhost:9090` — scrapes the backend running on the host at port `8000` |
| **Grafana** | `3001` | `3000` | HTTP | `http://localhost:3001` — login `admin` / `admin` (local dev only) |

## How to Manage the Stack

All command examples assume you are running them from the project root directory.

### Start the Stack
To start the services in the background and wait for them to pass their health checks:
```bash
docker compose -f infrastructure/docker/docker-compose.dev.yml up -d
```

### View Service Status & Health
To check the status and health checks of the running containers:
```bash
docker compose -f infrastructure/docker/docker-compose.dev.yml ps
```

### View Logs
To view combined logs or logs of a specific service:
```bash
# All services
docker compose -f infrastructure/docker/docker-compose.dev.yml logs -f

# Specific service (e.g., kafka)
docker compose -f infrastructure/docker/docker-compose.dev.yml logs -f kafka
```

### Stop the Stack (Preserving Volumes/Data)
To stop and remove the containers while **preserving** the data in the named volumes for future use:
```bash
docker compose -f infrastructure/docker/docker-compose.dev.yml down
```

### Stop the Stack and Remove Volumes (Full Clean Reset)
To stop and remove containers **AND** delete all persistent data in the named Docker volumes:
```bash
docker compose -f infrastructure/docker/docker-compose.dev.yml down -v
```

## Volumes & Persistence

The stack uses named Docker volumes to ensure development state is not lost when containers are recreated:
- `vistaar_postgres_data`: Persists PostgreSQL database schemas and data.
- `vistaar_redis_data`: Persists Redis data.
- `vistaar_kafka_data`: Persists Kafka logs/topics.
- `vistaar_prometheus_data`: Persists Prometheus's own metrics history.
- `vistaar_grafana_data`: Persists Grafana's own database (dashboards created outside the provisioned ones, users, etc.).

These volumes persist across normal `docker compose down` commands. They are only removed if you explicitly run `docker compose down -v`.
