---
title: Orchestrator
---

# Orchestrator

**Port:** `8000` (override with `ORCHESTRATOR_PORT`)
**Skill:** `orchestrate`
**Source:** `src/a2a_orchestrator/orchestrator/`

## What it does

Receives a freeform user request, plans a sequence of specialist-agent calls with Claude, dispatches each step over A2A streaming, and streams a synthesized natural-language answer.

## Card

```json
{
  "name": "orchestrator",
  "description": "Plan, dispatch, and synthesize across specialist agents.",
  "skills": [
    {
      "id": "orchestrate",
      "name": "orchestrate",
      "description": "Accept a freeform request, plan with specialist agents, return a synthesized answer.",
      "examples": [
        "Parse https://example.com/ramen and find any similar recipes I already have.",
        "Give me a vegan ramen recipe."
      ]
    }
  ]
}
```

## Files

| File | Purpose |
|---|---|
| `__main__.py` | FastAPI parent app: rate-limit middleware, OpenAI-compat router, static OpenAPI handler, mounts A2A sub-app at `/` |
| `executor.py` | `OrchestratorExecutor` — discovery, planning, dispatch loop, synthesis, history |
| `planner.py` | `PLAN_SCHEMA`, `build_plan()`, `substitute_placeholders()`, `synthesize()` |
| `openai_compat.py` | `/v1/models` and `/v1/chat/completions` (sync + SSE) |

## Why FastAPI wraps the A2A app

The A2A SDK gives you a `Starlette` application via `A2AStarletteApplication.build()`. To layer on the OpenAI-compat router, the static `/openapi.json` route, and our custom rate-limit middleware uniformly across every surface, the orchestrator wraps that Starlette app in a `FastAPI` parent and **mounts** the A2A app at `/`.

The mount is at `/` so the A2A SDK's well-known card path (`/.well-known/agent-card.json`) and JSON-RPC entrypoint (`POST /`) both keep their canonical URLs. FastAPI routes registered before the mount (`/v1/...`, `/openapi.json`) take precedence.

## Configuration knobs specific to orchestrator

| Variable | Default | Effect |
|---|---|---|
| `ORCHESTRATOR_PORT` | `8000` | Bind port |
| `A2A_DISCOVERY_URLS` | (unset) | Wins over `A2A_DISCOVERY_PORTS` if set |
| `A2A_DISCOVERY_PORTS` | `8001,8002,8003` | Used when URLs unset |
| `RATE_LIMIT` | `1200/minute` | Comma-separated `limits` specs |

See [Configuration](../getting-started/configuration.md) for the full list.

## Cross-references

- [Orchestration Loop](../architecture/orchestration-loop.md) — what `execute()` does step-by-step
- [Discovery](../architecture/discovery.md) — peer-card fetching
- [Conversation History](../architecture/history.md) — per-`contextId` cache
- [OpenAI-Compatible](../api/openai-compat.md) — the `/v1/...` surface
