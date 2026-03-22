"""Az CLI Runner — FastAPI application.

A containerised API service that executes Azure CLI commands in isolated sessions.
Designed for use by AI agents and automation workflows running in Azure Container Apps.
"""

from fastapi import FastAPI, HTTPException

from app.executor import AzCliExecutor
from app.models import AzCliRequest, AzCliResponse, ErrorResponse
from app.validator import CommandValidationError, parse_command, validate_command

app = FastAPI(
    title="Az CLI Runner",
    description=(
        "API-driven isolated Azure CLI runner. Submit Azure CLI commands to be "
        "executed under a specified Azure subscription using a service principal. "
        "Each execution runs in an isolated session to support concurrent operations "
        "across different subscriptions."
    ),
    version="0.1.0",
)

executor = AzCliExecutor()


@app.post(
    "/execute",
    response_model=AzCliResponse,
    responses={400: {"model": ErrorResponse}, 500: {"model": ErrorResponse}},
    summary="Execute an Azure CLI command",
    description=(
        "Execute an Azure CLI command under a specific Azure subscription. "
        "The service authenticates with a pre-configured service principal, "
        "sets the target subscription, and runs the command in an isolated session. "
        "Commands that modify authentication state (login, logout, account changes) "
        "are automatically rejected."
    ),
)
async def execute_command(request: AzCliRequest) -> AzCliResponse:
    """Execute an Azure CLI command in an isolated session.

    Validates the command, authenticates to the target subscription using
    a service principal, and executes the command. Each invocation uses
    a separate AZURE_CONFIG_DIR to ensure session isolation.

    Args:
        request: The command execution request containing the CLI command
                 and target subscription ID.

    Returns:
        AzCliResponse with the command output, exit code, and success status.

    Raises:
        HTTPException: 400 if the command fails validation.
        HTTPException: 500 if authentication or execution fails unexpectedly.
    """
    try:
        args = parse_command(request.command)
        validated_args = validate_command(args)
    except CommandValidationError as e:
        raise HTTPException(status_code=400, detail=e.message)

    try:
        return await executor.execute(validated_args, request.subscription_id)
    except RuntimeError as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.get(
    "/health",
    summary="Health check",
    description="Returns the health status of the service. Use this to verify the service is running.",
)
async def health_check() -> dict:
    """Health check endpoint.

    Returns a simple status indicator to confirm the service is operational.
    """
    return {"status": "healthy"}
