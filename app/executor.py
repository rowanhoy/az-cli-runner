"""Azure CLI command executor with session isolation.

Executes Azure CLI commands in isolated environments using per-session
AZURE_CONFIG_DIR directories. This ensures concurrent sessions under
different subscriptions do not interfere with each other.
"""

import asyncio
import os
import shutil
import tempfile
import uuid
from typing import Optional

from app.models import AzCliResponse


class AzCliExecutor:
    """Executes Azure CLI commands in isolated sessions.

    Each execution creates a temporary AZURE_CONFIG_DIR to ensure
    complete isolation between concurrent sessions. The service principal
    credentials are read from environment variables.
    """

    def __init__(self) -> None:
        self.client_id: Optional[str] = os.environ.get("AZURE_CLIENT_ID")
        self.client_secret: Optional[str] = os.environ.get("AZURE_CLIENT_SECRET")
        self.tenant_id: Optional[str] = os.environ.get("AZURE_TENANT_ID")

    def _check_credentials(self) -> None:
        """Verify that service principal credentials are configured.

        Raises:
            RuntimeError: If any required credential environment variable is missing.
        """
        missing = []
        if not self.client_id:
            missing.append("AZURE_CLIENT_ID")
        if not self.client_secret:
            missing.append("AZURE_CLIENT_SECRET")
        if not self.tenant_id:
            missing.append("AZURE_TENANT_ID")
        if missing:
            raise RuntimeError(
                f"Missing required environment variables: {', '.join(missing)}"
            )

    async def _run_az_command(
        self, args: list[str], env: dict[str, str]
    ) -> tuple[int, str, str]:
        """Run an az cli command as a subprocess.

        Args:
            args: The argument list to pass to 'az'.
            env: The environment variables for the subprocess.

        Returns:
            A tuple of (return_code, stdout, stderr).
        """
        process = await asyncio.create_subprocess_exec(
            "az",
            *args,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
            env=env,
        )
        stdout_bytes, stderr_bytes = await process.communicate()
        return (
            process.returncode or 0,
            stdout_bytes.decode("utf-8", errors="replace"),
            stderr_bytes.decode("utf-8", errors="replace"),
        )

    async def execute(
        self, command_args: list[str], subscription_id: str
    ) -> AzCliResponse:
        """Execute an Azure CLI command under an isolated session.

        Creates a temporary AZURE_CONFIG_DIR, authenticates with the service
        principal, sets the subscription, executes the command, and cleans up.

        Args:
            command_args: The validated argument list (without leading 'az').
            subscription_id: The Azure subscription ID to use.

        Returns:
            AzCliResponse with the command output and exit code.

        Raises:
            RuntimeError: If credentials are not configured or login fails.
        """
        self._check_credentials()

        session_id = uuid.uuid4().hex
        config_dir = tempfile.mkdtemp(prefix=f"az-cli-runner-{session_id}-")

        try:
            # Build isolated environment
            env = os.environ.copy()
            env["AZURE_CONFIG_DIR"] = config_dir

            # Login with service principal
            login_rc, login_stdout, login_stderr = await self._run_az_command(
                [
                    "login",
                    "--service-principal",
                    "--username",
                    self.client_id,
                    "--password",
                    self.client_secret,
                    "--tenant",
                    self.tenant_id,
                ],
                env=env,
            )
            if login_rc != 0:
                raise RuntimeError(f"az login failed (exit {login_rc}): {login_stderr}")

            # Set subscription
            sub_rc, _, sub_stderr = await self._run_az_command(
                ["account", "set", "--subscription", subscription_id],
                env=env,
            )
            if sub_rc != 0:
                raise RuntimeError(
                    f"az account set failed (exit {sub_rc}): {sub_stderr}"
                )

            # Execute the actual command
            rc, stdout, stderr = await self._run_az_command(command_args, env=env)

            return AzCliResponse(
                success=rc == 0,
                exit_code=rc,
                stdout=stdout,
                stderr=stderr,
            )
        finally:
            # Clean up the isolated config directory
            shutil.rmtree(config_dir, ignore_errors=True)
