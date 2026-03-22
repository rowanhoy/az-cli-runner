"""Az CLI Runner — FastAPI application.

A containerised API service that executes Azure CLI commands in isolated sessions.
"""

from contextlib import asynccontextmanager

from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import JSONResponse

from app.config import get_settings
from app.executor import AzCliExecutor
from app.models import AzCliRequest, AzCliResponse, ErrorResponse
from app.validator import CommandValidationError, parse_command, validate_command

settings = get_settings()


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Warm and tear down the subprocess session pool with app lifecycle."""
    await subprocess_executor.initialize()
    try:
        yield
    finally:
        await subprocess_executor.close()

app = FastAPI(
    title=settings.app_name,
    description=settings.app_description,
    version=settings.app_version,
    default_response_class=JSONResponse,
    lifespan=lifespan,
)

subprocess_executor = AzCliExecutor(settings)


@app.exception_handler(Exception)
async def unhandled_exception_handler(
    request: Request, exc: Exception
) -> JSONResponse:
    """Return a JSON error payload for unexpected server failures."""
    return JSONResponse(
        status_code=500,
        content={"detail": "Internal server error"},
    )


def _validate_request(request: AzCliRequest) -> tuple[list[str], str]:
    """Validate an execution request and resolve the subscription."""
    try:
        args = parse_command(request.command)
        validated_args = validate_command(args)
    except CommandValidationError as e:
        raise HTTPException(status_code=400, detail=e.message)

    subscription_id = request.subscription_id or settings.default_subscription_id
    if not subscription_id:
        raise HTTPException(
            status_code=400,
            detail=(
                "No subscription_id was provided and DEFAULT_SUBSCRIPTION_ID is not configured."
            ),
        )

    return validated_args, subscription_id


@app.post(
    "/execute",
    response_model=AzCliResponse,
    responses={400: {"model": ErrorResponse}, 500: {"model": ErrorResponse}},
    summary="Execute an Azure CLI command via az subprocess",
    description=(
        "Execute an Azure CLI command under a specific Azure subscription by "
        "shelling out to the az executable. The service authenticates with a "
        "pre-configured service principal, sets the target subscription, and runs "
        "the command in an isolated session. Commands that modify authentication "
        "state are automatically rejected."
    ),
)
async def execute_command(request: AzCliRequest) -> AzCliResponse:
    """Execute an Azure CLI command through the az subprocess path."""
    validated_args, subscription_id = _validate_request(request)

    try:
        return await subprocess_executor.execute(validated_args, subscription_id)
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
