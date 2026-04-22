---
title: Docker
---

# Docker

A single Dockerfile builds an image that contains all four agent entrypoints. The container's `CMD` selects which agent runs.

## Build

```bash
docker build -t a2a-orchestrator:local .
```

The build:

1. Starts from `python:3.12-slim`.
2. Installs `curl` (used by the healthcheck).
3. Copies the `uv` binary from `ghcr.io/astral-sh/uv`.
4. Creates a non-root user `a2a` (uid/gid 10001).
5. Installs runtime dependencies (`uv sync --frozen --no-dev --no-install-project`) — this layer caches across source changes.
6. Copies `src/` and `docs/openapi/` into the image.
7. Installs the project itself (`uv sync --frozen --no-dev`).
8. Drops to the non-root user.

`docs/openapi/` is bundled because the orchestrator serves the static merged spec from disk at `/openapi.json`.

## Entrypoint

```dockerfile
ENTRYPOINT ["python", "-m"]
CMD ["a2a_orchestrator.orchestrator"]
```

Override `CMD` to run a different agent:

```bash
docker run --rm -p 8001:8001 \
  -e ANTHROPIC_API_KEY=sk-ant-... \
  a2a-orchestrator:local a2a_orchestrator.recipe_url
```

## Healthcheck

```dockerfile
HEALTHCHECK --interval=30s --timeout=5s --start-period=10s --retries=3 \
    CMD curl -fsS http://localhost:${PORT:-8000}/.well-known/agent-card.json || exit 1
```

The check hits the agent card. Set `PORT` (or rely on the `8000` default) so the URL matches the agent that's running.

## Compose example

```yaml
services:
  orchestrator:
    image: a2a-orchestrator:local
    ports: ["8000:8000"]
    environment:
      ANTHROPIC_API_KEY: ${ANTHROPIC_API_KEY}
      A2A_DISCOVERY_URLS: http://recipe-url:8001,http://recipe-gen:8002
    depends_on: [recipe-url, recipe-gen]

  recipe-url:
    image: a2a-orchestrator:local
    command: a2a_orchestrator.recipe_url
    environment:
      ANTHROPIC_API_KEY: ${ANTHROPIC_API_KEY}

  recipe-gen:
    image: a2a-orchestrator:local
    command: a2a_orchestrator.recipe_gen
    environment:
      ANTHROPIC_API_KEY: ${ANTHROPIC_API_KEY}
```

The shell agent is omitted — it would need privileged Docker-in-Docker, which is undesirable in compose.
