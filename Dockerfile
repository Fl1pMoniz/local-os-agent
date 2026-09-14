# Multi-stage lightweight Linux container for Aperture Science GLaDOS Agent
FROM python:3.11-slim-bookworm

# Install Astral uv package manager binary
COPY --from=ghcr.io/astral-sh/uv:latest /uv /bin/uv

# Install system dependencies: curl (healthchecks), ffmpeg (audio/video), procps
RUN apt-get update && apt-get install -y --no-install-recommends \
    curl \
    ffmpeg \
    procps \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

# Set container execution and terminal environment variables
ENV PYTHONUNBUFFERED=1 \
    CONTAINER_MODE=true \
    UI_HOST=0.0.0.0 \
    UI_PORT=5000 \
    HEADLESS=true \
    UV_LINK_MODE=copy

# Copy dependency specifications first for optimal Docker layer caching
COPY pyproject.toml uv.lock README.md ./

# Install python dependencies without installing the project root yet
RUN uv sync --no-dev --frozen --no-install-project

# Copy application source tree
COPY . .

# Sync project root package into virtualenv
RUN uv sync --no-dev --frozen

# Expose Web UI terminal port
EXPOSE 5000

# Container healthcheck against local Web UI endpoint
HEALTHCHECK --interval=30s --timeout=5s --start-period=10s --retries=3 \
    CMD curl -f http://127.0.0.1:5000/api/state || exit 1

# Launch GLaDOS web application runner
CMD ["uv", "run", "glados-web"]

