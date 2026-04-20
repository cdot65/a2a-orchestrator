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
