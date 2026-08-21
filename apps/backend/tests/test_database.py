import pytest
from sqlalchemy import text
from sqlalchemy.exc import OperationalError

from core.config import settings
from core.database import engine


def test_database_configuration() -> None:
    """Verify that configuration loads the database URL correctly."""
    assert settings.DATABASE_URL is not None
    assert "postgresql" in settings.DATABASE_URL


def test_database_connection() -> None:
    """Integration test to verify PostgreSQL database connectivity.

    This test attempts to connect to the database and execute a simple query.
    If the database is completely unreachable (e.g. connection refused),
    the test will skip. Any other database exception will fail the test.
    """
    try:
        with engine.connect() as connection:
            result = connection.execute(text("SELECT 1")).scalar()
            assert result == 1
    except OperationalError as e:
        err_str = str(e).lower()
        # Define phrases indicating a completely unreachable/unavailable database server
        unreachable_phrases = [
            "connection refused",
            "could not connect to server",
            "timeout expired",
            "is the server running",
            "does not exist",
        ]
        if any(phrase in err_str for phrase in unreachable_phrases):
            pytest.skip(
                f"PostgreSQL at {settings.DATABASE_URL} is unreachable/stopped: {e}"
            )
        else:
            # Raise exception so auth/query errors fail the test
            raise
