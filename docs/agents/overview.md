---
title: Agents Overview
---

# Agents Overview

Four agents, each its own ASGI process, each a separate `Executor` implementation.

| Agent | Port | Skill ID | Purpose |
|---|---|---|---|
| [orchestrator](orchestrator.md) | 8000 | `orchestrate` | Plan + dispatch + synthesize |
| [recipe-url](recipe-url.md) | 8001 | `parse_recipe_url` | Scrape a URL into a structured Recipe |
| [recipe-gen](recipe-gen.md) | 8002 | `generate_recipe` | Generate a fresh structured Recipe |
| [shell](shell.md) | 8003 | `run_shell` | Run a sandboxed shell command |

## Common shape

Every agent implements the A2A executor interface:

```python
class MyExecutor:
    async def execute(self, context, event_queue) -> None: ...
    async def cancel(self, context, event_queue) -> None: ...
```

`context` exposes `task_id`, `context_id`, and `get_user_input() -> str`. `event_queue.enqueue_event(...)` accepts the A2A event types (`TaskStatusUpdateEvent`, `TaskArtifactUpdateEvent`).

The agent's `__main__.py` wires it up:

```python
handler = DefaultRequestHandler(agent_executor=MyExecutor(), task_store=InMemoryTaskStore())
a2a_app = A2AStarletteApplication(agent_card=agent_card, http_handler=handler).build()
uvicorn.run(a2a_app, host="0.0.0.0", port=port)
```

The orchestrator's `__main__.py` is slightly more involved — it wraps the A2A app in a FastAPI parent that adds the OpenAI-compat router, the static OpenAPI handler, and the rate-limit middleware. See `src/a2a_orchestrator/orchestrator/__main__.py`.

## Shared building blocks

| Module | Purpose |
|---|---|
| `common.a2a_helpers` | `build_agent_card`, `discover_agents`, `status_event`, `text_update`, `artifact_event` |
| `common.claude` | Anthropic client, `call_with_schema()` (tool-use forced JSON), `stream_text()` (synthesis) |
| `common.recipe` | `Recipe` Pydantic model + `recipe_json_schema()` for tool-use |
| `common.persistence` | Save a `Recipe` as `<slug>.json` + `<slug>.md` under `RECIPES_DIR` |
| `common.logging` | structlog setup; `get_logger(name)` |
| `common.ratelimit` | Per-IP rate limit middleware (orchestrator only) |
