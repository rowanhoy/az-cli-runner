# Az CLI Runner

API-driven isolated Azure CLI runner for Azure Container Apps. Submit Azure CLI commands to be executed under a specified subscription using a service principal. Each execution runs in an isolated session (separate `AZURE_CONFIG_DIR`) to support concurrent operations across different subscriptions.

## Features

- **Single endpoint** (`POST /execute`) accepts an Azure CLI command + subscription ID
- **Command validation** blocks dangerous commands (`az login`, `az logout`, `az account set/list/show/clear`)
- **Session isolation** via per-request temporary `AZURE_CONFIG_DIR` directories
- **Service principal auth** — credentials are read from environment variables
- **Health check** at `GET /health`

## Prerequisites

- Python 3.12+
- [uv](https://docs.astral.sh/uv/) package manager
- Azure CLI (`az`) installed (for production use)

## Quick Start

```bash
# Install dependencies
uv sync

# Run the server locally
uv run uvicorn app.main:app --reload --port 8000
```

## Environment Variables

| Variable | Description |
|---|---|
| `AZURE_CLIENT_ID` | Service principal application (client) ID |
| `AZURE_CLIENT_SECRET` | Service principal secret |
| `AZURE_TENANT_ID` | Azure AD tenant ID |

## API Usage

### Execute a command

```bash
curl -X POST http://localhost:8000/execute \
  -H "Content-Type: application/json" \
  -d '{
    "command": "az group list",
    "subscription_id": "12345678-1234-1234-1234-123456789abc"
  }'
```

### Health check

```bash
curl http://localhost:8000/health
```

### API docs

Interactive docs available at `http://localhost:8000/docs` when the server is running.

## Running Tests

```bash
uv run pytest -v
```

## Running Benchmarks

```bash
uv add psutil
python benchmarks/memory_benchmark.py --sessions 10 --mode subprocess
```

## Docker

```bash
# Build
docker build -t az-cli-runner .

# Run
docker run -p 8000:8000 \
  -e AZURE_CLIENT_ID=... \
  -e AZURE_CLIENT_SECRET=... \
  -e AZURE_TENANT_ID=... \
  az-cli-runner
```

## Project Structure

```
app/
  main.py          # FastAPI app with /execute and /health endpoints
  models.py        # Pydantic request/response models
  executor.py      # Az CLI execution with isolated config dirs
  validator.py     # Command validation and sanitization
tests/
  test_api.py      # API endpoint tests
  test_executor.py # Executor unit tests
  test_validator.py # Validator unit tests
benchmarks/
  memory_benchmark.py  # Concurrent session memory testing
Dockerfile
```
API driven isolated Az CLI runner - designed for use by agents
