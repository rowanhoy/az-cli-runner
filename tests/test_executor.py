"""Tests for the Az CLI executor."""

import os
from unittest.mock import patch

import pytest

from app.executor import AzCliExecutor


@pytest.fixture
def executor_with_creds():
    """Create an executor with mock credentials."""
    with patch.dict(
        os.environ,
        {
            "AZURE_CLIENT_ID": "test-client-id",
            "AZURE_CLIENT_SECRET": "test-client-secret",
            "AZURE_TENANT_ID": "test-tenant-id",
        },
    ):
        yield AzCliExecutor()


@pytest.fixture
def executor_without_creds():
    """Create an executor without credentials."""
    with patch.dict(os.environ, {}, clear=True):
        yield AzCliExecutor()


class TestAzCliExecutor:
    """Tests for AzCliExecutor."""

    def test_check_credentials_missing_all(self, executor_without_creds):
        with pytest.raises(RuntimeError, match="AZURE_CLIENT_ID"):
            executor_without_creds._check_credentials()

    def test_check_credentials_present(self, executor_with_creds):
        # Should not raise
        executor_with_creds._check_credentials()

    @pytest.mark.asyncio
    async def test_execute_success(self, executor_with_creds):
        """Test successful command execution with mocked subprocess."""

        async def mock_run(args, env):
            if args[0] == "login":
                return (0, '{"success": true}', "")
            if args[0] == "account" and args[1] == "set":
                return (0, "", "")
            return (0, '["result"]', "")

        with patch.object(
            executor_with_creds, "_run_az_command", side_effect=mock_run
        ):
            result = await executor_with_creds.execute(
                ["group", "list"], "12345678-1234-1234-1234-123456789abc"
            )
            assert result.success is True
            assert result.exit_code == 0
            assert result.stdout == '["result"]'

    @pytest.mark.asyncio
    async def test_execute_login_failure(self, executor_with_creds):
        """Test that login failure raises RuntimeError."""

        async def mock_run(args, env):
            if args[0] == "login":
                return (1, "", "Login failed")
            return (0, "", "")

        with patch.object(
            executor_with_creds, "_run_az_command", side_effect=mock_run
        ):
            with pytest.raises(RuntimeError, match="az login failed"):
                await executor_with_creds.execute(
                    ["group", "list"], "12345678-1234-1234-1234-123456789abc"
                )

    @pytest.mark.asyncio
    async def test_execute_subscription_failure(self, executor_with_creds):
        """Test that subscription set failure raises RuntimeError."""

        async def mock_run(args, env):
            if args[0] == "login":
                return (0, "", "")
            if args[0] == "account":
                return (1, "", "Subscription not found")
            return (0, "", "")

        with patch.object(
            executor_with_creds, "_run_az_command", side_effect=mock_run
        ):
            with pytest.raises(RuntimeError, match="az account set failed"):
                await executor_with_creds.execute(
                    ["group", "list"], "12345678-1234-1234-1234-123456789abc"
                )

    @pytest.mark.asyncio
    async def test_execute_command_failure(self, executor_with_creds):
        """Test non-zero exit code from the actual command."""

        async def mock_run(args, env):
            if args[0] == "login":
                return (0, "", "")
            if args[0] == "account":
                return (0, "", "")
            return (2, "", "Resource not found")

        with patch.object(
            executor_with_creds, "_run_az_command", side_effect=mock_run
        ):
            result = await executor_with_creds.execute(
                ["group", "show", "--name", "missing"],
                "12345678-1234-1234-1234-123456789abc",
            )
            assert result.success is False
            assert result.exit_code == 2
            assert result.stderr == "Resource not found"

    @pytest.mark.asyncio
    async def test_execute_uses_isolated_config_dir(self, executor_with_creds):
        """Test that each execution uses a unique AZURE_CONFIG_DIR."""
        config_dirs_seen = []

        async def mock_run(args, env):
            config_dirs_seen.append(env.get("AZURE_CONFIG_DIR"))
            return (0, "", "")

        with patch.object(
            executor_with_creds, "_run_az_command", side_effect=mock_run
        ):
            await executor_with_creds.execute(
                ["group", "list"], "12345678-1234-1234-1234-123456789abc"
            )
            # Should have been called 3 times: login, account set, command
            assert len(config_dirs_seen) == 3
            # All should use the same config dir within a single execution
            assert len(set(config_dirs_seen)) == 1
            # Should be a temp directory
            assert "az-cli-runner" in config_dirs_seen[0]

    @pytest.mark.asyncio
    async def test_config_dir_cleanup(self, executor_with_creds):
        """Test that config dir is cleaned up after execution."""
        config_dir_ref = []

        async def mock_run(args, env):
            config_dir_ref.append(env.get("AZURE_CONFIG_DIR"))
            return (0, "", "")

        with patch.object(
            executor_with_creds, "_run_az_command", side_effect=mock_run
        ):
            await executor_with_creds.execute(
                ["group", "list"], "12345678-1234-1234-1234-123456789abc"
            )

        # Config dir should be cleaned up
        assert not os.path.exists(config_dir_ref[0])
