import os


class Settings:
    """Centralized application and infrastructure settings."""

    def __init__(self) -> None:
        self.APP_ENV: str = os.getenv("APP_ENV", "development")
        self.APP_NAME: str = os.getenv("APP_NAME", "vistaar")
        self.APP_VERSION: str = os.getenv("APP_VERSION", "1.0.0")

        self.BACKEND_HOST: str = os.getenv("BACKEND_HOST", "127.0.0.1")
        raw_port = os.getenv("BACKEND_PORT", "8000")
        try:
            self.BACKEND_PORT: int = int(raw_port)
        except ValueError as err:
            raise ValueError(f"BACKEND_PORT must be an integer: {err}") from err

        self.DATABASE_URL: str = os.getenv(
            "DATABASE_URL",
            "postgresql://db_user:db_password@127.0.0.1:5433/vistaar_db",
        )
        self.REDIS_URL: str = os.getenv("REDIS_URL", "redis://127.0.0.1:6379/0")
        self.KAFKA_BOOTSTRAP_SERVERS: str = os.getenv(
            "KAFKA_BOOTSTRAP_SERVERS", "127.0.0.1:9092"
        )

        self.validate()

    def validate(self) -> None:
        """Validate configuration values."""
        valid_envs = {"development", "testing", "staging", "production"}
        if self.APP_ENV not in valid_envs:
            raise ValueError(f"APP_ENV must be one of {valid_envs}")

        if not self.APP_NAME.strip():
            raise ValueError("APP_NAME cannot be empty")

        if not self.APP_VERSION.strip():
            raise ValueError("APP_VERSION cannot be empty")

        if not self.BACKEND_HOST.strip():
            raise ValueError("BACKEND_HOST cannot be empty")

        if not (1 <= self.BACKEND_PORT <= 65535):
            raise ValueError("BACKEND_PORT must be between 1 and 65535")

        if not (
            self.DATABASE_URL.startswith("postgresql://")
            or self.DATABASE_URL.startswith("postgres://")
        ):
            raise ValueError(
                "DATABASE_URL must start with postgresql:// or postgres://"
            )

        if not (
            self.REDIS_URL.startswith("redis://")
            or self.REDIS_URL.startswith("rediss://")
        ):
            raise ValueError("REDIS_URL must start with redis:// or rediss://")

        if not self.KAFKA_BOOTSTRAP_SERVERS.strip():
            raise ValueError("KAFKA_BOOTSTRAP_SERVERS cannot be empty")


settings = Settings()
