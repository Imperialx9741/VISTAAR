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
    # APP_ENV=production below now also requires a real JWT_SECRET — see
    # test_placeholder_jwt_secret_rejected_outside_development.
    monkeypatch.setenv("JWT_SECRET", "a-real-randomly-generated-secret-value")

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


def test_placeholder_jwt_secret_rejected_outside_development(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Security review finding, 2026-09-02: booting with the committed
    placeholder JWT_SECRET anywhere but local development would let
    anyone who has read this repository forge a valid token for any
    account — see core/config.py's own comment on this check."""
    monkeypatch.setenv("APP_ENV", "production")
    monkeypatch.delenv("JWT_SECRET", raising=False)
    with pytest.raises(ValueError, match="JWT_SECRET is still the default"):
        Settings()

    monkeypatch.setenv("APP_ENV", "staging")
    with pytest.raises(ValueError, match="JWT_SECRET is still the default"):
        Settings()

    monkeypatch.setenv("APP_ENV", "testing")
    with pytest.raises(ValueError, match="JWT_SECRET is still the default"):
        Settings()


def test_placeholder_jwt_secret_still_allowed_in_development(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The default APP_ENV — local development never has to set
    JWT_SECRET just to start the app, same convenience every other
    placeholder-default secret in this codebase already gets."""
    monkeypatch.setenv("APP_ENV", "development")
    monkeypatch.delenv("JWT_SECRET", raising=False)

    dev_settings = Settings()

    assert dev_settings.JWT_SECRET == (
        "placeholder_jwt_secret_key_minimum_32_characters_long"
    )


def test_real_jwt_secret_allowed_in_production(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("APP_ENV", "production")
    monkeypatch.setenv("JWT_SECRET", "a-real-randomly-generated-secret-value")

    prod_settings = Settings()

    assert prod_settings.APP_ENV == "production"


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
