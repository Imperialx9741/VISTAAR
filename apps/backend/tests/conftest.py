import os

# Disable Sentry for the whole test run (2026-09-08) — must run here, at
# conftest.py's module level, before anything imports core.config: that
# module now calls `load_dotenv()` at its own import time (same date),
# which pulls a real SENTRY_DSN in from the repo-root `.env` once one is
# configured there. Without this, every local `pytest` run would submit
# real "events" to that Sentry project on interpreter shutdown (observed
# directly — `sentry_sdk`'s own flush prints "Sentry is attempting to
# send N pending events" at the end of a run with a real DSN loaded).
# Setting os.environ here — not something inside core/config.py itself —
# keeps this a test-only concern; core.config's own SENTRY_DSN default
# stays whatever a real deployment's `.env`/environment provides.
os.environ["SENTRY_DSN"] = ""

# --- Task 2.7B test-isolation correction ---------------------------------
# Redirect DATABASE_URL to a dedicated test database (vistaar_test_db)
# before anything else in this process imports core.config or
# core.database — core.config.settings is a module-level singleton that
# reads DATABASE_URL exactly once, at import time (src/core/config.py),
# and core.database's engine/SessionLocal bind to that URL at import time
# too (src/core/database.py). pytest always imports this conftest.py
# before collecting any test module in this directory, so this is early
# enough for every test — including the API tests that exercise real
# writes through FastAPI's `get_db` dependency, which no test overrides —
# not just the two dedicated "integration" test files. See
# tests/_integration_db.py for the full rationale.
from _integration_db import (  # noqa: E402
    ensure_admin_settings_seeded,
    ensure_database_exists,
    resolve_test_database_url,
    run_migrations,
)

os.environ["DATABASE_URL"] = resolve_test_database_url()

# Must run here, at conftest.py's module (import) level — not inside a
# fixture. Every DB-backed test module in this directory decides whether
# to skip via `pytestmark = pytest.mark.skipif(not _infra_available(), ...)`,
# which pytest evaluates at COLLECTION time (when it imports each test
# module), before any fixture — including a session-scoped autouse one —
# ever runs. On a database that doesn't exist yet (e.g. the very first
# run in a fresh environment), a fixture-based bootstrap would only take
# effect starting on the *second* invocation, silently skipping every
# Postgres-dependent test on the first. Running this at import time
# instead means conftest.py (always imported before its directory's test
# modules) has already created and migrated the test database before any
# module's `_infra_available()` collection-time check runs.
if ensure_database_exists(os.environ["DATABASE_URL"]):
    run_migrations()

# Unconditional, every session — see ensure_admin_settings_seeded()'s own
# docstring for why run_migrations() above is not enough by itself
# (ADR-0048's admin.settings has no Create endpoint, so a prior
# session's truncate_integration_tables() run can leave it empty for
# this one to inherit).
ensure_admin_settings_seeded(os.environ["DATABASE_URL"])

import pytest  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402

from main import app  # noqa: E402


@pytest.fixture(scope="session")
def client() -> TestClient:
    return TestClient(app)
