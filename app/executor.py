"""Azure CLI executor with pooled subprocess sessions.

The executor maintains a bounded pool of authenticated `AZURE_CONFIG_DIR`
directories. Each pooled session is logged in once using the shared service
principal credentials and can then be reused for many commands. Request-level
subscription targeting is handled by injecting `--subscription`, which avoids
running `az login` and `az account set` on every request.
"""

import asyncio
from dataclasses import dataclass
import json
import os
import shutil
import tempfile
import time
import uuid

from app.config import Settings
from app.models import AzCliInvocationTiming, AzCliResponse, AzCliTiming


@dataclass(slots=True)
class _PooledSession:
    """Reusable authenticated Azure CLI session state."""

    config_dir: str
    env: dict[str, str]


class BaseAzCliExecutor:
    """Shared helpers for Azure CLI execution paths."""

    def __init__(self, settings: Settings) -> None:
        self.settings = settings

    @staticmethod
    def _force_json_output(args: list[str]) -> list[str]:
        """Normalize command arguments so Azure CLI always returns JSON."""
        normalized_args: list[str] = []
        skip_next = False

        for arg in args:
            if skip_next:
                skip_next = False
                continue

            if arg in {"-o", "--output"}:
                skip_next = True
                continue

            if arg.startswith("--output=") or arg.startswith("-o="):
                continue

            normalized_args.append(arg)

        return [*normalized_args, "--output", "json"]

    def _login_args(self) -> list[str]:
        """Build the Azure CLI login arguments."""
        return [
            "login",
            "--service-principal",
            "--username",
            self.settings.azure_client_id,
            "--password",
            self.settings.azure_client_secret,
            "--tenant",
            self.settings.azure_tenant_id,
            "--output",
            "none",
        ]

    @staticmethod
    def _with_subscription(args: list[str], subscription_id: str) -> list[str]:
        """Normalize command arguments to enforce one subscription value."""
        normalized_args: list[str] = []
        skip_next = False

        for arg in args:
            if skip_next:
                skip_next = False
                continue

            if arg == "--subscription":
                skip_next = True
                continue

            if arg.startswith("--subscription="):
                continue

            normalized_args.append(arg)

        return [*normalized_args, "--subscription", subscription_id]

    @staticmethod
    def _parse_json_output(stdout: str) -> object | None:
        """Parse JSON command output when present."""
        if not stdout.strip():
            return None

        try:
            return json.loads(stdout)
        except json.JSONDecodeError as exc:
            raise RuntimeError("az command returned invalid JSON output") from exc


class AzCliExecutor(BaseAzCliExecutor):
    """Executes Azure CLI commands through pooled `az` subprocess sessions."""

    def __init__(self, settings: Settings) -> None:
        super().__init__(settings)
        self._initialization_lock = asyncio.Lock()
        self._session_queue: asyncio.Queue[_PooledSession] = asyncio.Queue(
            maxsize=self.settings.max_concurrent_sessions
        )
        self._initialized = False

    async def _run_az_command(
        self, args: list[str], env: dict[str, str]
    ) -> tuple[int, str, str, AzCliInvocationTiming]:
        """Run an az cli command as a subprocess."""
        start = time.perf_counter()
        process = await asyncio.create_subprocess_exec(
            "az",
            *args,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
            env=env,
        )
        startup_elapsed = time.perf_counter() - start
        stdout_bytes, stderr_bytes = await process.communicate()
        total_elapsed = time.perf_counter() - start
        return (
            process.returncode or 0,
            stdout_bytes.decode("utf-8", errors="replace"),
            stderr_bytes.decode("utf-8", errors="replace"),
            AzCliInvocationTiming(
                total_seconds=total_elapsed,
                startup_seconds=startup_elapsed,
                execution_seconds=total_elapsed - startup_elapsed,
            ),
        )

    async def _authenticate_session(self, config_dir: str) -> dict[str, str]:
        """Authenticate one reusable session config directory."""
        env = os.environ.copy()
        env["AZURE_CONFIG_DIR"] = config_dir

        login_rc, _, login_stderr, _ = await self._run_az_command(
            self._login_args(),
            env=env,
        )
        if login_rc != 0:
            raise RuntimeError(f"az login failed (exit {login_rc}): {login_stderr}")

        return env

    async def initialize(self) -> None:
        """Create and authenticate the bounded session pool once."""
        if self._initialized:
            return

        async with self._initialization_lock:
            if self._initialized:
                return

            template_dir = tempfile.mkdtemp(prefix="az-cli-runner-template-")

            try:
                await self._authenticate_session(template_dir)

                for _ in range(self.settings.max_concurrent_sessions):
                    session_id = uuid.uuid4().hex
                    session_dir = tempfile.mkdtemp(prefix=f"az-cli-runner-{session_id}-")
                    shutil.rmtree(session_dir, ignore_errors=True)
                    shutil.copytree(template_dir, session_dir)
                    env = os.environ.copy()
                    env["AZURE_CONFIG_DIR"] = session_dir
                    self._session_queue.put_nowait(
                        _PooledSession(config_dir=session_dir, env=env)
                    )
            finally:
                shutil.rmtree(template_dir, ignore_errors=True)

            self._initialized = True

    async def close(self) -> None:
        """Clean up pooled authenticated session directories."""
        while not self._session_queue.empty():
            session = self._session_queue.get_nowait()
            shutil.rmtree(session.config_dir, ignore_errors=True)
            self._session_queue.task_done()

        self._initialized = False

    async def execute(
        self, command_args: list[str], subscription_id: str
    ) -> AzCliResponse:
        """Execute an Azure CLI command using a pooled authenticated session."""
        await self.initialize()

        request_start = time.perf_counter()
        acquire_start = time.perf_counter()
        session = await self._session_queue.get()
        session_acquire_seconds = time.perf_counter() - acquire_start
        try:
            rc, stdout, stderr, command_timing = await self._run_az_command(
                self._force_json_output(
                    self._with_subscription(command_args, subscription_id)
                ),
                env=session.env,
            )
            parsed_result = self._parse_json_output(stdout)
        finally:
            release_start = time.perf_counter()
            self._session_queue.put_nowait(session)
            session_release_seconds = time.perf_counter() - release_start

        return AzCliResponse(
            success=rc == 0,
            exit_code=rc,
            result=parsed_result,
            stderr=stderr,
            timings=AzCliTiming(
                total_seconds=time.perf_counter() - request_start,
                session_acquire_seconds=session_acquire_seconds,
                command=command_timing,
                session_release_seconds=session_release_seconds,
            ),
        )
