---
title: Contributing
---

# Contributing

## Workflow

1. Fork + branch.
2. `uv sync` to set up the venv.
3. Make changes.
4. `make fmt && make lint && make test` before opening a PR.
5. If you touch routes or schemas, regenerate the OpenAPI specs:

   ```bash
   uv run python scripts/generate_openapi.py
   ```

   …and commit the regenerated `docs/openapi/*.json` files.

## Adding a new agent

1. Create `src/a2a_orchestrator/<name>/` with `__init__.py`, `__main__.py`, and `executor.py`.
2. Implement an `Executor` class with `async execute(self, context, event_queue)` and `async cancel(...)`.
3. Provide a `build_card(url)` function that returns an agent-card dict via `common.a2a_helpers.build_agent_card(...)`.
4. Wire `__main__.py` like the existing agents — see `recipe_gen/__main__.py` for the minimal shape.
5. Add the new port to `.env.example` and the run-all script.
6. Add the new base URL to the orchestrator's discovery default if it should be on by default; otherwise leave callers to set `A2A_DISCOVERY_URLS`/`A2A_DISCOVERY_PORTS` themselves.
7. Document the agent under `docs/agents/<name>.md` and add it to `mkdocs.yml`.

## Style

- Type hints everywhere.
- Pydantic v2 for any structured data crossing a process boundary.
- structlog (`common.logging.get_logger`) for logs — never bare `print`.
- Keep agent executors small; push reusable bits into `common/`.

## Commit messages

Conventional-commit style is used in the project history:

```
feat(orchestrator): server-side contextId history replay
fix(discovery): overwrite card.url with reachable URL
chore: ruff format
```

Keep the subject under ~70 characters.
