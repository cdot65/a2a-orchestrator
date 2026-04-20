FROM python:3.12-slim

# Install curl (needed for HEALTHCHECK) and clean up
RUN apt-get update && apt-get install -y --no-install-recommends curl && rm -rf /var/lib/apt/lists/*

# Install uv
COPY --from=ghcr.io/astral-sh/uv:latest /uv /usr/local/bin/uv

# Create non-root user
RUN groupadd --gid 10001 a2a && useradd --uid 10001 --gid 10001 --no-create-home --shell /sbin/nologin a2a

WORKDIR /app

# Copy dependency files first for layer caching
COPY pyproject.toml uv.lock ./

# Install runtime deps only
RUN uv sync --frozen --no-dev

# Copy source and static assets
COPY src/ ./src/
COPY docs/openapi/ ./docs/openapi/

# Drop to non-root
USER 10001

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1

HEALTHCHECK --interval=30s --timeout=5s --start-period=10s --retries=3 \
    CMD curl -fsS http://localhost:${PORT:-8000}/.well-known/agent-card.json || exit 1

ENTRYPOINT ["uv", "run", "python", "-m"]
CMD ["a2a_orchestrator.orchestrator"]
