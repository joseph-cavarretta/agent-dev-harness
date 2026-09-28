from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class AppConfig(BaseSettings):
    """Typed settings: the only place environment variables are read."""

    model_config = SettingsConfigDict(env_file=".env", extra="forbid")

    log_level: str = Field(default="INFO", description="Root log level.")


def get_settings() -> AppConfig:
    """Load settings. Call once, at the entry point, and pass the result down."""
    return AppConfig()
