"""Shared pytest configuration."""

import os

import pytest

from app.config import get_settings

os.environ.setdefault("AZURE_CLIENT_ID", "test-client-id")
os.environ.setdefault("AZURE_CLIENT_SECRET", "test-client-secret")
os.environ.setdefault("AZURE_TENANT_ID", "test-tenant-id")
os.environ.setdefault(
    "DEFAULT_SUBSCRIPTION_ID",
    "12345678-1234-1234-1234-123456789abc",
)


@pytest.fixture(autouse=True)
def clear_settings_cache():
    """Ensure settings changes in tests do not leak through the cache."""
    get_settings.cache_clear()
    yield
    get_settings.cache_clear()