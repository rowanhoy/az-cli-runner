# Az CLI Runner

API-driven Azure CLI runner for Azure Container Apps. Submit Azure CLI commands to be executed under a specified subscription using a service principal. The service keeps a bounded pool of authenticated subprocess sessions so commands can run concurrently without paying the full login cost on every request.

## Features

- **Single execution endpoint** backed by a pooled subprocess executor
- **Command validation** blocks dangerous commands (`az login`, `az logout`, `az account set/list/show/clear`)
- **Session reuse** via a bounded pool of authenticated `AZURE_CONFIG_DIR` directories
- **JSON output enforced** for executed Azure CLI commands, regardless of user-supplied output flags
- **Service principal auth** — credentials are read from environment variables
- **Configurable concurrency limit** via `MAX_CONCURRENT_SESSIONS`
- **Health check** at `GET /health`

## Prerequisites

- Python 3.12+
- [uv](https://docs.astral.sh/uv/) package manager
- Azure CLI (`az`) installed when running outside Docker

## Quick Start

```bash
# Install dependencies
uv sync

# Create local configuration
cp .env.example .env

# Run the server locally
uv run uvicorn app.main:app --reload --port 8000
```

The application loads settings from environment variables and from a local `.env` file via `pydantic-settings`. Importing `app.main` validates the required Azure credentials immediately, so startup fails if they are missing or blank.

## Environment Variables

| Variable | Description |
|---|---|
| `AZURE_CLIENT_ID` | Service principal application (client) ID |
| `AZURE_CLIENT_SECRET` | Service principal secret |
| `AZURE_TENANT_ID` | Azure AD tenant ID |
| `DEFAULT_SUBSCRIPTION_ID` | Default subscription used when `subscription_id` is omitted from API requests or benchmarks |
| `MAX_CONCURRENT_SESSIONS` | Size of the authenticated subprocess session pool and the maximum in-flight command count |

## API Usage

### Execute a command

```bash
curl -X POST http://localhost:8000/execute \
  -H "Content-Type: application/json" \
  -d '{
    "command": "az group list"
  }'
```

The API itself always responds with JSON, and executed Azure CLI commands are forced to run with `--output json` so successful commands are returned as structured JSON in the `result` field instead of a raw `stdout` string. If `subscription_id` is omitted, the service falls back to `DEFAULT_SUBSCRIPTION_ID`. The executor injects `--subscription` automatically for each request, so the service does not need to run `az account set` per command.

Successful execution responses include a `timings` object with a per-phase breakdown for pool acquisition and command execution.

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
uv sync --dev

# Start the server separately and capture its PID
uv run uvicorn app.main:app --host 127.0.0.1 --port 8000 &
SERVER_PID=$!

uv run python benchmarks/memory_benchmark.py \
  --server-pid "$SERVER_PID" \
  --sessions 10
```

The benchmark calls the live API over HTTP and samples the running server's process tree memory. By default it uses `DEFAULT_SUBSCRIPTION_ID` and `az group list`.
It also prints the average per-phase timings returned by the API so you can identify where session latency is concentrated.

### Benchmark Snapshot

The following measurements were taken locally with `MAX_CONCURRENT_SESSIONS=10` and the default benchmark command `az group list`.

| Sessions | Wall Time | Avg Session Time | Peak Memory | Memory Delta | Est. Per Session |
|---|---:|---:|---:|---:|---:|
| 1 | 0.76s | 0.76s | 133.0 MB | 82.8 MB | 82.8 MB |
| 2 | 1.46s | 1.41s | 187.5 MB | 137.2 MB | 68.6 MB |
| 3 | 2.14s | 1.86s | 239.9 MB | 189.5 MB | 63.2 MB |
| 5 | 3.86s | 3.61s | 391.2 MB | 340.7 MB | 68.1 MB |
| 10 | 7.73s | 7.40s | 815.9 MB | 765.3 MB | 76.5 MB |

For this benchmark, incremental process-tree memory ranged from about `63 MB` to `83 MB` per active session. A conservative planning estimate is `70-80 MB` per active session for this command shape.

## Docker

The container image installs Azure CLI from the project's Python dependencies instead of inheriting the stale `mcr.microsoft.com/azure-cli` base image.

```bash
# Build
docker build -t az-cli-runner .

# Run
docker run -p 8000:8000 \
  --env-file .env \
  az-cli-runner
```

## Project Structure

```
app/
  config.py        # Pydantic settings loaded from env vars and .env
  main.py          # FastAPI app with one pooled subprocess execute endpoint
  models.py        # Pydantic request/response models
  executor.py      # Pooled subprocess Az CLI execution path
  validator.py     # Command validation and sanitization
tests/
  conftest.py      # Test environment bootstrap for settings
  test_config.py   # Settings validation tests
  test_api.py      # API endpoint tests
  test_executor.py # Executor unit tests
  test_validator.py # Validator unit tests
benchmarks/
  memory_benchmark.py  # Concurrent session memory testing
Dockerfile
```
