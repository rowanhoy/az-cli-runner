"""Application settings for the Az CLI Runner."""

from functools import lru_cache

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Central application settings loaded from env vars and `.env`."""

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
        case_sensitive=True,
        str_strip_whitespace=True,
        populate_by_name=True,
    )

    app_name: str = "Az CLI Runner"
    app_description: str = (
        "API-driven isolated Azure CLI runner. Submit Azure CLI commands to be "
        "executed under a specified Azure subscription using a service principal. "
        "Each execution runs in an isolated session to support concurrent operations "
        "across different subscriptions."
    )
    app_version: str = "0.1.0"
    azure_client_id: str = Field(min_length=1, validation_alias="AZURE_CLIENT_ID")
    azure_client_secret: str = Field(
        min_length=1,
        validation_alias="AZURE_CLIENT_SECRET",
    )
    azure_tenant_id: str = Field(min_length=1, validation_alias="AZURE_TENANT_ID")
    default_subscription_id: str | None = Field(
        default=None,
        pattern=r"^[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{12}$",
        validation_alias="DEFAULT_SUBSCRIPTION_ID",
    )
    max_concurrent_sessions: int = Field(
        default=4,
        ge=1,
        validation_alias="MAX_CONCURRENT_SESSIONS",
    )


@lru_cache
def get_settings() -> Settings:
    """Load and cache application settings."""
    return Settings()