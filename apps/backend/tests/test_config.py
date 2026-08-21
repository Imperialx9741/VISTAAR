import pytest

from core.config import Settings, settings


def test_default_configuration_loads() -> None:
    """Verify that default settings load with expected values."""
    assert settings.APP_ENV in {"development", "testing", "staging", "production"}
    assert settings.APP_NAME == "vistaar"
    assert settings.APP_VERSION == "1.0.0"
    assert settings.BACKEND_HOST == "127.0.0.1"
    assert settings.BACKEND_PORT == 8000
    assert "postgresql" in settings.DATABASE_URL
    assert "redis" in settings.REDIS_URL
    assert settings.KAFKA_BOOTSTRAP_SERVERS == "127.0.0.1:9092"


def test_custom_environment_overrides(monkeypatch: pytest.MonkeyPatch) -> None:
    """Verify environment variable overrides load properly."""
    monkeypatch.setenv("APP_ENV", "production")
    monkeypatch.setenv("APP_NAME", "vistaar-prod")
    monkeypatch.setenv("APP_VERSION", "2.0.0")
    monkeypatch.setenv("BACKEND_HOST", "0.0.0.0")
    monkeypatch.setenv("BACKEND_PORT", "9000")
    monkeypatch.setenv("DATABASE_URL", "postgresql://user:pass@db:5432/db")
    monkeypatch.setenv("REDIS_URL", "redis://cache:6379/1")
    monkeypatch.setenv("KAFKA_BOOTSTRAP_SERVERS", "kafka:9092")

    custom_settings = Settings()
    assert custom_settings.APP_ENV == "production"
    assert custom_settings.APP_NAME == "vistaar-prod"
    assert custom_settings.APP_VERSION == "2.0.0"
    assert custom_settings.BACKEND_HOST == "0.0.0.0"
    assert custom_settings.BACKEND_PORT == 9000
    assert custom_settings.DATABASE_URL == "postgresql://user:pass@db:5432/db"
    assert custom_settings.REDIS_URL == "redis://cache:6379/1"
    assert custom_settings.KAFKA_BOOTSTRAP_SERVERS == "kafka:9092"


def test_invalid_app_env(monkeypatch: pytest.MonkeyPatch) -> None:
    """Verify invalid APP_ENV raises ValueError."""
    monkeypatch.setenv("APP_ENV", "invalid_env")
    with pytest.raises(ValueError, match="APP_ENV must be one of"):
        Settings()


def test_empty_string_configurations(monkeypatch: pytest.MonkeyPatch) -> None:
    """Verify empty string configuration fields raise ValueError."""
    monkeypatch.setenv("APP_NAME", "   ")
    with pytest.raises(ValueError, match="APP_NAME cannot be empty"):
        Settings()

    monkeypatch.undo()
    monkeypatch.setenv("KAFKA_BOOTSTRAP_SERVERS", "")
    with pytest.raises(ValueError, match="KAFKA_BOOTSTRAP_SERVERS cannot be empty"):
        Settings()


def test_invalid_backend_port(monkeypatch: pytest.MonkeyPatch) -> None:
    """Verify invalid BACKEND_PORT raises ValueError."""
    monkeypatch.setenv("BACKEND_PORT", "not_an_int")
    with pytest.raises(ValueError, match="BACKEND_PORT must be an integer"):
        Settings()

    monkeypatch.undo()
    monkeypatch.setenv("BACKEND_PORT", "70000")
    with pytest.raises(ValueError, match="BACKEND_PORT must be between 1 and 65535"):
        Settings()


def test_invalid_url_schemes(monkeypatch: pytest.MonkeyPatch) -> None:
    """Verify invalid URL schemes raise ValueError."""
    monkeypatch.setenv("DATABASE_URL", "mysql://user:pass@localhost/db")
    with pytest.raises(ValueError, match="DATABASE_URL must start with"):
        Settings()

    monkeypatch.undo()
    monkeypatch.setenv("REDIS_URL", "http://localhost:6379")
    with pytest.raises(ValueError, match="REDIS_URL must start with"):
        Settings()
