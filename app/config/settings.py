"""Process-level settings.

Fields are added as features arrive.
"""

from typing import Literal

from pydantic_settings import BaseSettings, SettingsConfigDict

LogLevel = Literal["DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"]


class Settings(BaseSettings):
    """Top-level application settings."""

    log_level: LogLevel = "INFO"
    cors_allow_origins: tuple[str, ...] = ()
    database_url: str = "sqlite:///./dustops.db"
    # R9 mitigation: when running on synthetic data, set DUSTOPS_MOCK_MODE=true
    # so /api/v1/meta reports it and the dashboard (Phase J) can show
    # a "DEMO DATA" badge.
    mock_mode: bool = False

    model_config = SettingsConfigDict(
        env_prefix="DUSTOPS_",
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )


def get_settings() -> Settings:
    return Settings()
