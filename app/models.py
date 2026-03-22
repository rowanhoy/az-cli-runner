"""Pydantic models for the Az CLI Runner API.

These models define the request and response schemas for the API.
"""

from typing import Any

from pydantic import BaseModel, Field


class AzCliInvocationTiming(BaseModel):
    """Timing for one Azure CLI invocation."""

    total_seconds: float = Field(
        ...,
        description="Total elapsed time for the Azure CLI invocation.",
    )
    startup_seconds: float | None = Field(
        default=None,
        description=(
            "Time spent starting the process or initializing the CLI call before it begins "
            "producing output. This is populated for subprocess execution."
        ),
    )
    execution_seconds: float | None = Field(
        default=None,
        description=(
            "Time spent waiting for the Azure CLI invocation to complete after startup. "
            "This is populated for subprocess execution."
        ),
    )


class AzCliTiming(BaseModel):
    """Execution timing breakdown for one request."""

    total_seconds: float = Field(
        ...,
        description="Total elapsed time for the full request execution path.",
    )
    session_acquire_seconds: float = Field(
        ...,
        description="Time spent waiting for and acquiring a pooled authenticated session.",
    )
    command: AzCliInvocationTiming = Field(
        ...,
        description="Timing for the requested Azure CLI command.",
    )
    session_release_seconds: float = Field(
        ...,
        description="Time spent returning the pooled session back to the executor.",
    )


class AzCliRequest(BaseModel):
    """Request to execute an Azure CLI command.

    Submit an Azure CLI command to be executed under a specific Azure subscription.
    The command will be executed in an isolated session using a pre-configured service principal.
    Commands that modify authentication state (login, logout, account changes) are rejected.
    """

    command: str = Field(
        ...,
        description=(
            "The Azure CLI command to execute, e.g. 'az group list' or "
            "'az vm show --resource-group myRg --name myVm'. "
            "Do NOT include 'az login', 'az logout', or 'az account set' commands — "
            "these are handled automatically by the service."
        ),
        examples=["az group list", "az vm list --resource-group myResourceGroup"],
    )
    subscription_id: str | None = Field(
        default=None,
        description=(
            "The Azure Subscription ID (UUID) under which the command should be executed. "
            "If omitted, the service uses DEFAULT_SUBSCRIPTION_ID from configuration."
        ),
        pattern=r"^[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{12}$",
        examples=["12345678-1234-1234-1234-123456789abc"],
    )


class AzCliResponse(BaseModel):
    """Response from an Azure CLI command execution.

    Contains the parsed JSON result of the executed command, stderr,
    and the process exit code. A non-zero exit code indicates the command failed.
    """

    success: bool = Field(
        ...,
        description="Whether the command executed successfully (exit code 0).",
    )
    exit_code: int = Field(
        ...,
        description="The process exit code. 0 indicates success, non-zero indicates failure.",
    )
    result: Any = Field(
        ...,
        description=(
            "The parsed JSON output from the Azure CLI command. This is null when "
            "the command produces no stdout."
        ),
    )
    stderr: str = Field(
        ...,
        description="The standard error output from the Azure CLI command, if any.",
    )
    timings: AzCliTiming | None = Field(
        default=None,
        description="Optional execution timing breakdown for profiling and diagnostics.",
    )


class ErrorResponse(BaseModel):
    """Error response returned when a request is rejected.

    This is returned when the submitted command fails validation,
    for example when attempting to run a prohibited command.
    """

    detail: str = Field(
        ...,
        description="A human-readable description of the error.",
    )
