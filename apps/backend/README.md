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
- **State**: Infrastructure foundation only. **Zero** business topics, producers, consumers, or domain event handlers are implemented yet.

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

## Docker Containerization Guide

The backend application can be containerized and run locally for development and testing.

### Prerequisites
- Docker Desktop or Docker Engine installed and running.

### 1. Build the Backend Image
Run the following command from the `apps/backend/` directory:
```bash
docker build -t vistaar-backend:latest .
```

### 2. Run the Container
Start the backend container, mapping host port `8000` to container port `8000`:
```bash
docker run -d --name vistaar-backend -p 8000:8000 vistaar-backend:latest
```

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

*Note: Infrastructure dependencies (like PostgreSQL, Redis, Kafka) are not integrated in this standalone container and will be configured in subsequent tasks.*
