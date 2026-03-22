FROM python:3.12-alpine

# Install uv
COPY --from=ghcr.io/astral-sh/uv:latest /uv /uvx /bin/

# Install runtime libraries and temporary build dependencies for Azure CLI.
RUN apk add --no-cache ca-certificates libffi libgcc libstdc++ openssl \
	&& apk add --no-cache --virtual .build-deps build-base cargo libffi-dev openssl-dev

# Set working directory
WORKDIR /app

ENV PATH="/app/.venv/bin:$PATH"

# Copy dependency files first for better layer caching
COPY pyproject.toml uv.lock ./

# Install dependencies (no dev deps in production)
RUN uv sync --frozen --no-dev --no-install-project \
	&& apk del .build-deps

# Copy application code
COPY app/ app/

# Expose port
EXPOSE 8000

# Run the FastAPI server
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
