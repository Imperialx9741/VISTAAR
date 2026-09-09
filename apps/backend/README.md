# VISTAAR Backend Application

This is the backend application skeleton for VISTAAR, a ride-matching platform.

## Prerequisites

- **Required Python Version**: Python 3.12.x (do not use Python 3.15 alpha/pre-release).

## Developer Guide (Windows)

### 1. Create the Virtual Environment
To create a clean virtual environment using Python 3.12 on Windows, open your shell (PowerShell or CMD) and run:
```powershell
# Using the Python Launcher to select Python 3.12:
py -3.12 -m venv .venv
```
The virtual environment will be created in the `apps/backend/.venv/` directory.

### 2. Activate the Virtual Environment
- **Using PowerShell**:
  ```powershell
  .venv\Scripts\Activate.ps1
  ```
- **Using Command Prompt (CMD)**:
  ```cmd
  .venv\Scripts\activate.bat
  ```

### 3. Verify the Python Version
Ensure the active environment reports Python 3.12.x:
```powershell
python --version
```

### 4. Install Project Dependencies
Install the required packages in development mode:
```powershell
python -m pip install --upgrade pip
pip install -e .[dev]
```

> `uv.lock` in this directory is used only by the production
> `Dockerfile` (`uv sync --frozen`, for a reproducible, reviewable
> shipped image — security-review-pass-2-2026-09-03.md §3.2) — plain
> local development, as above, is unaffected and does not need `uv` at
> all. Regenerate it (`uv lock`) and commit the result whenever
> `pyproject.toml`'s dependencies change; the Docker build fails loudly
> if the two ever drift out of sync.

### 5. Run the Backend
Start the FastAPI server locally:
```powershell
uvicorn src.main:app --reload
```
The application will run at [http://127.0.0.1:8000](http://127.0.0.1:8000). You can check:
- Health endpoint: `GET /health`
- Swagger documentation: `GET /docs`

### 6. Run the Backend Tests
Run the test suite using pytest:
```powershell
pytest
```

### 7. Deactivate the Environment
To exit the active virtual environment:
```powershell
deactivate
```

## Code Quality Tools

The project uses the following code-quality tools:
1. **Code Formatting**: [Ruff](https://github.com/astral-sh/ruff)
2. **Linting**: [Ruff](https://github.com/astral-sh/ruff)
3. **Type Checking**: [MyPy](https://github.com/python/mypy)

### 1. Run Formatting
To automatically format the code:
```powershell
ruff format src tests
```

### 2. Check Formatting
To verify if code complies with formatting rules:
```powershell
ruff format --check src tests
```

### 3. Run Linting
To check code logic issues and styling warnings:
```powershell
ruff check src tests
```

### 4. Run Type Checking
To check static type constraints:
```powershell
mypy src tests
```

### 5. Run Tests
To run pytest tests:
```powershell
pytest
```

## Infrastructure Configuration

### 1. Centralized Settings
The backend application uses a centralized configuration system in [`src/core/config.py`](file:///c:/Users/kumar/Downloads/VISTAAR/apps/backend/src/core/config.py) through the `Settings` class (`settings` instance). Environment variables serve as the authoritative runtime source, falling back to safe local development defaults when unconfigured.

### 2. Supported Configuration Variables & Defaults

| Category | Environment Variable | Default Value | Validation Rules |
| :--- | :--- | :--- | :--- |
| **Application** | `APP_ENV` | `development` | Must be `development`, `testing`, `staging`, or `production` |
| **Application** | `APP_NAME` | `vistaar` | Cannot be empty or whitespace-only |
| **Application** | `APP_VERSION` | `1.0.0` | Cannot be empty or whitespace-only |
| **Backend Host** | `BACKEND_HOST` | `127.0.0.1` | Cannot be empty or whitespace-only |
| **Backend Port** | `BACKEND_PORT` | `8000` | Must be integer between `1` and `65535` |
| **PostgreSQL** | `DATABASE_URL` | `postgresql://db_user:db_password@127.0.0.1:5433/vistaar_db` | Must start with `postgresql://` or `postgres://` |
| **Redis** | `REDIS_URL` | `redis://127.0.0.1:6379/0` | Must start with `redis://` or `rediss://` |
| **Kafka** | `KAFKA_BOOTSTRAP_SERVERS` | `127.0.0.1:9092` | Cannot be empty or whitespace-only |

> [!NOTE]
> **Configuration-Only Status**: Redis and Kafka settings are validated for configuration accuracy. Actual client connections, producers, consumers, and caching logic will be introduced in subsequent tasks. The application and test suite run without requiring active Redis or Kafka containers.

## Database & Migrations

### 1. Overview
- **Database**: **PostgreSQL** is used as the primary relational database.
- **ORM**: **SQLAlchemy** is used for database access and session management.
- **Migrations**: **Alembic** is used to handle schema migrations.
- **Configuration**: The `DATABASE_URL` is supplied through environment configuration, defaulting to:
  `postgresql://db_user:db_password@127.0.0.1:5433/vistaar_db`
- **State**: No business or domain tables have been introduced yet.

### 2. Start PostgreSQL Infrastructure
To start the PostgreSQL development service in the background:
```bash
# Run from the project root directory
docker compose -f infrastructure/docker/docker-compose.dev.yml up -d
```

### 3. Verify Database Connectivity
You can verify the connectivity of the backend database in two ways:
- **FastAPI Endpoint**: Start the server (`uvicorn src.main:app --reload`) and request `GET http://127.0.0.1:8000/health/db`.
- **Integration Tests**: Run the pytest suite while the database is running:
  ```powershell
  pytest tests/test_database.py
  ```
  *(Note: The database connectivity test will skip automatically if the server is stopped, ensuring unit tests can always be run offline or in CI).*

### 4. Alembic Migration Commands
Run all Alembic commands from the `apps/backend/` directory:
- **Check current migration state**:
  ```bash
  alembic current
  ```
- **Generate a new migration**:
  ```bash
  alembic revision --autogenerate -m "migration description"
  ```
- **Apply migrations**:
  ```bash
  alembic upgrade head
  ```
- **Revert migrations**:
  ```bash
  alembic downgrade -1
  ```

### 5. Manual diagnostic scripts and the dev database

`DATABASE_URL`'s default (`core/config.py`) points at the local
docker-compose Postgres — the same database `uvicorn`/the Admin Web/the
mobile app use for real manual testing. `pytest` never touches it
(`tests/conftest.py` forces `DATABASE_URL` to an isolated
`vistaar_test_db` before any test module even imports `core.config` —
see `tests/_integration_db.py`'s own docstring for the history of why
that exists: every DB-backed test used to run against this exact dev
database, and the resulting pollution — thousands of rows from two
runs on 2026-08-21/22 — was still being cleaned up as of 2026-09-08).

That isolation only covers `pytest`. **A one-off script that imports
`core.database.SessionLocal()` directly — `python -c "..."`, a
throwaway `.py` file, anything that isn't run through `pytest` — talks
to the real dev database, with no cleanup.** This includes diagnostic
scripts written during an AI-assisted session to reproduce a bug end-
to-end (exactly the technique used to diagnose several issues in this
project's history) — those are exactly as capable of leaving permanent
rows behind as the pre-isolation test runs were.

If you (or an assistant) need to run one:
- Prefer calling into the service/domain layer with fabricated
  in-memory arguments where possible, rather than round-tripping
  through the real DB, when the question doesn't require persistence.
- When a real DB round-trip is genuinely needed, use an obviously
  fake, greppable phone number/identifier (a repeated-digit prefix,
  e.g. `+919000000xxx`, is already the informal convention in this
  project's own diagnostic history) so the rows are trivially
  findable and excludable later, and clean them up in the same
  session once the diagnosis is done — don't leave them for someone
  else to puzzle over.
- Never run a full feature-verification flow (e.g. "does the whole
  signup→approval→ride lifecycle work") against this database from a
  script instead of `pytest` — that's exactly the shape of the
  original 2026-08-21/22 pollution.

## Redis Integration Foundation

### 1. Overview & Role
- **Role**: **Redis** serves as an infrastructure dependency for future caching, session management, rate limiting, and pub/sub capabilities.
- **Library**: Uses the standard `redis` Python client with `redis.asyncio` support.
- **Configuration**: The `REDIS_URL` is supplied through centralized `Settings`, defaulting to:
  `redis://127.0.0.1:6379/0`
- **State**: Infrastructure foundation only. Caching, sessions, rate limiting, OTP, queues, locks, and business repositories are **NOT** implemented yet.

### 2. Local Redis Container
Start the Task 13 infrastructure stack to run the Redis container:
```bash
docker compose -f infrastructure/docker/docker-compose.dev.yml up -d
```

### 3. Verify Redis Connectivity
You can verify Redis connectivity in two ways:
- **FastAPI Endpoint**: Start the server (`uvicorn src.main:app --reload`) and request `GET http://127.0.0.1:8000/health/redis`.
- **Integration & Lifecycle Tests**: Run the Redis pytest suite:
  ```powershell
  pytest tests/test_redis.py
  ```
  *(Note: Redis tests skip gracefully if the server is unreachable, keeping unit test runs independent).*

## Kafka Integration Foundation

### 1. Overview & Role
- **Role**: **Kafka** serves as the asynchronous event-streaming infrastructure dependency for future domain events and inter-service messaging.
- **Library**: Uses `aiokafka` (`AIOKafkaAdminClient`) for asynchronous broker communication and cluster metadata queries.
- **Configuration**: The `KAFKA_BOOTSTRAP_SERVERS` target is supplied through centralized `Settings`, defaulting to:
  `127.0.0.1:9092`
- **Resource Lifecycle**: The connection lifecycle is strictly managed via `check_kafka_connection()`, which starts the admin client, queries broker metadata (`describe_cluster()`), and guarantees teardown (`await admin.close()`) in a `finally` block.
- **State**: `shared/outbox_publisher.py` (ADR-0017) is a real producer, publishing every domain transition's outbox row; `modules/notification/consumer.py` (ADR-0038) is a real consumer, covering 4 event types. Both run in-process (main.py's lifespan), not as separate worker processes.

### 2. Local Kafka Container
Start the Task 13 infrastructure stack (Kafka running in KRaft mode):
```bash
docker compose -f infrastructure/docker/docker-compose.dev.yml up -d
```

### 3. Verify Kafka Connectivity
You can verify Kafka connectivity in two ways:
- **FastAPI Endpoint**: Start the server (`uvicorn src.main:app --reload`) and request `GET http://127.0.0.1:8000/health/kafka`.
- **Integration & Lifecycle Tests**: Run the Kafka pytest suite:
  ```powershell
  pytest tests/test_kafka.py
  ```
  *(Note: Kafka tests skip gracefully if the broker is unreachable, keeping unit test runs independent).*

## Background Worker (Celery)

### 1. Overview & Role
- **Role**: Background Worker Foundation (ADR-0039, owner-approved). Runs scheduled jobs that don't fit `main.py`'s in-process asyncio model — currently five periodic tasks, all in `modules/notification/tasks.py` (promotion/document expiry warnings, scheduled broadcast dispatch, one bounded FAILED-SMS/PUSH retry, ADR-0075) plus `modules/ride/tasks.py` (promoting due scheduled rides) — see `shared/celery_app.py`'s own `beat_schedule` for the authoritative, up-to-date list.
- **Broker/backend**: The same Redis instance as `REDIS_URL` — no separate infrastructure.
- **Process model**: Celery workers are a genuinely separate OS process from the FastAPI app (unlike the outbox publisher/notification consumer above) — nothing in `main.py` starts or depends on this.

### 2. Run It Locally
Start the dev infrastructure stack first (Redis + Postgres, `docker compose -f infrastructure/docker/docker-compose.dev.yml up -d`), then, from `apps/backend/`:
```bash
celery -A shared.celery_app worker --beat --loglevel=info
```
This combines Celery's scheduler (Beat) and its worker pool in one process — see ADR-0039 Decision 2 for why this stays a single process rather than two.

### 3. Verify It's Working
```bash
celery -A shared.celery_app inspect ping
```
should report one node online. To run a task immediately instead of waiting for its schedule:
```python
from modules.notification.tasks import check_expiring_promotions_task
check_expiring_promotions_task.delay()
```

## Docker Containerization Guide

The backend application can be containerized and run locally for development and testing. The image is a multi-stage build (ADR-0035): a builder stage installs the production dependencies declared in `pyproject.toml` (`[project].dependencies`, not the `dev` group) into a venv via `uv`, and the runtime stage copies that venv plus the `src/` tree, runs as a non-root user, and exposes a Docker `HEALTHCHECK` against `/health`.

### Prerequisites
- Docker Desktop or Docker Engine installed and running.

### 1. Build the Backend Image
Run the following command from the `apps/backend/` directory:
```bash
docker build -t vistaar-backend:latest .
```

### 2. Run the Container
Start the backend container, mapping host port `8000` to container port `8000`. It needs `DATABASE_URL`, `REDIS_URL`, and the other settings `core/config.py` reads (see `.env.example`) — pass them with `--env-file` or individual `-e` flags, and join the dev network (`infrastructure/docker/docker-compose.dev.yml`) so `postgres`/`redis`/`kafka` resolve by service name:
```bash
docker run -d --name vistaar-backend -p 8000:8000 \
  --network vistaar_dev_network \
  --env-file ../../.env \
  vistaar-backend:latest
```
Kafka being unavailable does not crash the process — the outbox publisher retries its connection in the background (`main.py`'s `lifespan()`), so the API still serves traffic without it.

### 3. Access Health Endpoint
Verify that the server starts successfully and is serving traffic:
```bash
curl http://127.0.0.1:8000/health
# Returns: {"status":"OK"}
```

### 4. Stop and Remove the Container
To clean up and remove the running container:
```bash
docker stop vistaar-backend
docker rm vistaar-backend
```

*Note: For a real deployment target (not local Docker), see `infrastructure/kubernetes/` and `infrastructure/terraform/aws/` — Amazon EKS, per ADR-0063 (supersedes ADR-0035's earlier DigitalOcean choice). `infrastructure/terraform/digitalocean/` is superseded and kept only for history — do not use it.*
