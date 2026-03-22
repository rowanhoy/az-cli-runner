"""Tests for the pooled Az CLI executor."""

import asyncio
from pathlib import Path
import tempfile
from unittest.mock import patch

import pytest

from app.config import Settings
from app.executor import AzCliExecutor, _PooledSession
from app.models import AzCliInvocationTiming


@pytest.fixture
def settings_with_creds():
    """Create validated settings with mock credentials."""
    return Settings(
        azure_client_id="test-client-id",
        azure_client_secret="test-client-secret",
        azure_tenant_id="test-tenant-id",
        max_concurrent_sessions=2,
        _env_file=None,
    )


@pytest.fixture
def executor_with_creds(settings_with_creds):
    """Create an executor with mock credentials."""
    return AzCliExecutor(settings_with_creds)


class TestAzCliExecutor:
    """Tests for AzCliExecutor."""

    @staticmethod
    def _timing(total_seconds: float = 0.01) -> AzCliInvocationTiming:
        return AzCliInvocationTiming(
            total_seconds=total_seconds,
            startup_seconds=0.001,
            execution_seconds=total_seconds - 0.001,
        )

    def test_force_json_output_appends_json_flag(self, executor_with_creds):
        assert executor_with_creds._force_json_output(["group", "list"]) == [
            "group",
            "list",
            "--output",
            "json",
        ]

    def test_force_json_output_overrides_existing_format(self, executor_with_creds):
        assert executor_with_creds._force_json_output(
            ["group", "list", "--output", "table"]
        ) == ["group", "list", "--output", "json"]

    def test_with_subscription_appends_subscription(self, executor_with_creds):
        assert executor_with_creds._with_subscription(
            ["group", "list"],
            "12345678-1234-1234-1234-123456789abc",
        ) == [
            "group",
            "list",
            "--subscription",
            "12345678-1234-1234-1234-123456789abc",
        ]

    def test_with_subscription_overrides_existing_flag(self, executor_with_creds):
        assert executor_with_creds._with_subscription(
            [
                "group",
                "list",
                "--subscription",
                "aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa",
            ],
            "12345678-1234-1234-1234-123456789abc",
        ) == [
            "group",
            "list",
            "--subscription",
            "12345678-1234-1234-1234-123456789abc",
        ]

    @pytest.mark.asyncio
    async def test_initialize_authenticates_once_and_populates_pool(
        self, executor_with_creds
    ):
        template_dirs: list[str] = []

        async def mock_authenticate(config_dir: str):
            Path(config_dir, "marker.txt").write_text("ready", encoding="utf-8")
            template_dirs.append(config_dir)
            return {"AZURE_CONFIG_DIR": config_dir}

        with patch.object(
            executor_with_creds,
            "_authenticate_session",
            side_effect=mock_authenticate,
        ) as mock_auth:
            await executor_with_creds.initialize()

        assert mock_auth.await_count == 1
        assert len(template_dirs) == 1
        assert executor_with_creds._session_queue.qsize() == 2

        sessions = [executor_with_creds._session_queue.get_nowait() for _ in range(2)]
        try:
            for session in sessions:
                assert Path(session.config_dir, "marker.txt").read_text(encoding="utf-8") == "ready"
        finally:
            for session in sessions:
                executor_with_creds._session_queue.put_nowait(session)

        await executor_with_creds.close()

    @pytest.mark.asyncio
    async def test_execute_success_uses_pooled_session(self, executor_with_creds):
        session_dir = tempfile.mkdtemp(prefix="az-cli-runner-test-")
        executor_with_creds._initialized = True
        executor_with_creds._session_queue.put_nowait(
            _PooledSession(
                config_dir=session_dir,
                env={"AZURE_CONFIG_DIR": session_dir},
            )
        )

        executed_args = []

        async def mock_run(args, env):
            executed_args.append((args, env["AZURE_CONFIG_DIR"]))
            return (0, '["result"]', "", self._timing())

        with patch.object(executor_with_creds, "_run_az_command", side_effect=mock_run):
            result = await executor_with_creds.execute(
                ["group", "list"], "12345678-1234-1234-1234-123456789abc"
            )

        assert result.success is True
        assert result.exit_code == 0
        assert result.result == ["result"]
        assert result.timings is not None
        assert result.timings.session_acquire_seconds >= 0
        assert result.timings.command.total_seconds >= 0
        assert result.timings.session_release_seconds >= 0
        assert executed_args == [
            (
                [
                    "group",
                    "list",
                    "--subscription",
                    "12345678-1234-1234-1234-123456789abc",
                    "--output",
                    "json",
                ],
                session_dir,
            )
        ]

        await executor_with_creds.close()

    @pytest.mark.asyncio
    async def test_execute_invalid_json_output_raises_runtime_error(
        self, executor_with_creds
    ):
        session_dir = tempfile.mkdtemp(prefix="az-cli-runner-test-")
        executor_with_creds._initialized = True
        executor_with_creds._session_queue.put_nowait(
            _PooledSession(config_dir=session_dir, env={"AZURE_CONFIG_DIR": session_dir})
        )

        async def mock_run(args, env):
            return (0, "not-json", "", self._timing())

        with patch.object(executor_with_creds, "_run_az_command", side_effect=mock_run):
            with pytest.raises(RuntimeError, match="invalid JSON output"):
                await executor_with_creds.execute(
                    ["group", "list"],
                    "12345678-1234-1234-1234-123456789abc",
                )

        assert executor_with_creds._session_queue.qsize() == 1
        await executor_with_creds.close()

    @pytest.mark.asyncio
    async def test_execute_waits_for_available_session(self, settings_with_creds):
        executor = AzCliExecutor(
            settings_with_creds.model_copy(update={"max_concurrent_sessions": 1})
        )
        session_dir = tempfile.mkdtemp(prefix="az-cli-runner-test-")
        executor._initialized = True
        executor._session_queue.put_nowait(
            _PooledSession(config_dir=session_dir, env={"AZURE_CONFIG_DIR": session_dir})
        )

        active_calls = 0
        max_active_calls = 0

        async def mock_run(args, env):
            nonlocal active_calls, max_active_calls
            active_calls += 1
            max_active_calls = max(max_active_calls, active_calls)
            await asyncio.sleep(0.05)
            active_calls -= 1
            return (0, "[]", "", self._timing(0.05))

        with patch.object(executor, "_run_az_command", side_effect=mock_run):
            await asyncio.gather(
                executor.execute(
                    ["group", "list"],
                    "12345678-1234-1234-1234-123456789abc",
                ),
                executor.execute(
                    ["group", "list"],
                    "12345678-1234-1234-1234-123456789abc",
                ),
            )

        assert max_active_calls == 1
        await executor.close()

    @pytest.mark.asyncio
    async def test_close_cleans_up_session_directories(self, executor_with_creds):
        session_dirs = [tempfile.mkdtemp(prefix="az-cli-runner-test-") for _ in range(2)]
        executor_with_creds._initialized = True
        for session_dir in session_dirs:
            executor_with_creds._session_queue.put_nowait(
                _PooledSession(config_dir=session_dir, env={"AZURE_CONFIG_DIR": session_dir})
            )

        await executor_with_creds.close()

        assert executor_with_creds._initialized is False
        assert executor_with_creds._session_queue.qsize() == 0
        for session_dir in session_dirs:
            assert not Path(session_dir).exists()
