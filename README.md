# A2A Orchestrator

Four A2A-compliant agents on localhost:

| Agent        | Port | Skill                         |
|--------------|------|-------------------------------|
| orchestrator | 8000 | `orchestrate`                 |
| recipe-url   | 8001 | `parse_recipe_url`            |
| recipe-gen   | 8002 | `generate_recipe`             |
| shell        | 8003 | `run_shell` (Docker sandbox)  |

The orchestrator auto-discovers the other three at startup, plans with Claude
Haiku 4.5, dispatches sequentially, and returns a synthesized answer.

## Setup

1. Install [uv](https://docs.astral.sh/uv/).
2. `uv sync`
3. `cp .env.example .env` and fill in `ANTHROPIC_API_KEY`.
4. `make shell-image` (requires Docker running).

## Run

```bash
make run-all
```

All four agents start in the foreground. Ctrl-C stops them.

## Try it

```bash
curl -s http://localhost:8000/.well-known/agent-card.json | jq .
```

Send a streaming request (adjust to current A2A client shape as needed):

```bash
curl -N -X POST http://localhost:8000/ \
  -H 'content-type: application/json' \
  -d '{
    "jsonrpc": "2.0",
    "id": "1",
    "method": "message/stream",
    "params": {
      "message": {
        "role": "user",
        "parts": [{"kind": "text", "text": "Give me a vegan ramen recipe."}],
        "messageId": "m1"
      }
    }
  }'
```

Generated recipes land in `./recipes/` as `.json` and `.md`.

### API Reference

**Static OpenAPI specs** — pre-generated, always available:

| File | Description |
|------|-------------|
| `docs/openapi/orchestrator.openapi.json` | Full spec: A2A + OpenAI-compat paths |
| `docs/openapi/recipe-url.openapi.json` | Recipe URL parser |
| `docs/openapi/recipe-gen.openapi.json` | Recipe generator |
| `docs/openapi/shell.openapi.json` | Shell agent |
| `docs/openapi/a2a-protocol.openapi.json` | Shared A2A protocol surface |

Each running agent also serves its spec at runtime:

```bash
curl http://localhost:8000/openapi.json   # orchestrator (A2A + OpenAI-compat)
curl http://localhost:8001/openapi.json   # recipe-url
curl http://localhost:8002/openapi.json   # recipe-gen
curl http://localhost:8003/openapi.json   # shell
```

**OpenAI-compatible chat API** (orchestrator only):

| Endpoint | Description |
|----------|-------------|
| `GET /v1/models` | List available models |
| `POST /v1/chat/completions` | Chat completion (set `"stream": true` for SSE) |
| `GET /v1/openapi.json` | FastAPI-generated spec for the OpenAI-compat surface only |
| `GET /v1/docs` | Swagger UI for the OpenAI-compat surface |

Example:

```bash
curl -s -X POST http://localhost:8000/v1/chat/completions \
  -H 'content-type: application/json' \
  -d '{
    "model": "a2a-orchestrator",
    "messages": [{"role": "user", "content": "Give me a vegan ramen recipe"}],
    "stream": false
  }' | jq .
```

## Docs

Full project documentation lives at [https://cdot65.github.io/a2a-orchestrator/](https://cdot65.github.io/a2a-orchestrator/) — architecture, agent internals, OpenAI-compat surface, and deployment notes.

## Deploy to Kubernetes (example)

The `k8s/` directory contains example manifests for deploying the orchestrator + the two stateless agents behind Traefik on a Talos cluster. Treat as a reference, not a turnkey deploy.

- **Manifests + walkthrough:** [`k8s/README.md`](k8s/README.md)
- **Cluster prerequisites:** [`k8s/cluster-setup/README.md`](k8s/cluster-setup/README.md)

The shell agent is excluded from the k8s example (requires Docker-in-Docker for sandboxing).

## Test

```bash
make test
```

## Layout

- `src/a2a_orchestrator/common/` — shared model, Claude helper, persistence, A2A helpers
- `src/a2a_orchestrator/orchestrator/` — planner + dispatch loop
- `src/a2a_orchestrator/recipe_url/` — fetch + extract + structure
- `src/a2a_orchestrator/recipe_gen/` — structured generation
- `src/a2a_orchestrator/shell/` — Dockerized sandboxed shell
