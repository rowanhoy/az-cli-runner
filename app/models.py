"""Pydantic models for the Az CLI Runner API.

These models define the request and response schemas for the API.
They are designed to be self-documenting for agent consumption.
"""

from pydantic import BaseModel, Field


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
    subscription_id: str = Field(
        ...,
        description=(
            "The Azure Subscription ID (UUID) under which the command should be executed. "
            "The service will authenticate and set this subscription before running the command."
        ),
        pattern=r"^[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{12}$",
        examples=["12345678-1234-1234-1234-123456789abc"],
    )


class AzCliResponse(BaseModel):
    """Response from an Azure CLI command execution.

    Contains the result of the executed command including stdout, stderr,
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
    stdout: str = Field(
        ...,
        description="The standard output from the Azure CLI command.",
    )
    stderr: str = Field(
        ...,
        description="The standard error output from the Azure CLI command, if any.",
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
