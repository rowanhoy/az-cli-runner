"""Tests for application settings loading."""

import pytest
from pydantic import ValidationError

from app.config import Settings, get_settings


class TestSettings:
    """Tests for Settings."""

    def test_get_settings_reads_environment(self, monkeypatch):
        monkeypatch.setenv("AZURE_CLIENT_ID", "env-client-id")
        monkeypatch.setenv("AZURE_CLIENT_SECRET", "env-client-secret")
        monkeypatch.setenv("AZURE_TENANT_ID", "env-tenant-id")
        monkeypatch.setenv(
            "DEFAULT_SUBSCRIPTION_ID",
            "12345678-1234-1234-1234-123456789abc",
        )
        monkeypatch.setenv("MAX_CONCURRENT_SESSIONS", "7")

        settings = get_settings()

        assert settings.azure_client_id == "env-client-id"
        assert settings.azure_client_secret == "env-client-secret"
        assert settings.azure_tenant_id == "env-tenant-id"
        assert (
            settings.default_subscription_id
            == "12345678-1234-1234-1234-123456789abc"
        )
        assert settings.max_concurrent_sessions == 7

    def test_missing_required_settings_raise_validation_error(self, monkeypatch):
        monkeypatch.delenv("AZURE_CLIENT_ID", raising=False)
        monkeypatch.delenv("AZURE_CLIENT_SECRET", raising=False)
        monkeypatch.delenv("AZURE_TENANT_ID", raising=False)

        with pytest.raises(ValidationError):
            Settings(_env_file=None)

    def test_settings_load_from_dotenv_file(self, monkeypatch, tmp_path):
        env_file = tmp_path / ".env"
        env_file.write_text(
            "AZURE_CLIENT_ID=dotenv-client-id\n"
            "AZURE_CLIENT_SECRET=dotenv-client-secret\n"
            "AZURE_TENANT_ID=dotenv-tenant-id\n"
            "DEFAULT_SUBSCRIPTION_ID=12345678-1234-1234-1234-123456789abc\n"
            "MAX_CONCURRENT_SESSIONS=6\n",
            encoding="utf-8",
        )

        monkeypatch.chdir(tmp_path)
        monkeypatch.delenv("AZURE_CLIENT_ID", raising=False)
        monkeypatch.delenv("AZURE_CLIENT_SECRET", raising=False)
        monkeypatch.delenv("AZURE_TENANT_ID", raising=False)

        settings = Settings()

        assert settings.azure_client_id == "dotenv-client-id"
        assert settings.azure_client_secret == "dotenv-client-secret"
        assert settings.azure_tenant_id == "dotenv-tenant-id"
        assert (
            settings.default_subscription_id
            == "12345678-1234-1234-1234-123456789abc"
        )
        assert settings.max_concurrent_sessions == 6

    def test_default_subscription_is_optional(self, monkeypatch):
        monkeypatch.delenv("DEFAULT_SUBSCRIPTION_ID", raising=False)

        settings = Settings(
            azure_client_id="env-client-id",
            azure_client_secret="env-client-secret",
            azure_tenant_id="env-tenant-id",
            _env_file=None,
        )

        assert settings.default_subscription_id is None
        assert settings.max_concurrent_sessions == 4

    def test_max_concurrent_sessions_must_be_positive(self):
        with pytest.raises(ValidationError):
            Settings(
                azure_client_id="env-client-id",
                azure_client_secret="env-client-secret",
                azure_tenant_id="env-tenant-id",
                max_concurrent_sessions=0,
                _env_file=None,
            )