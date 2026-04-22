---
title: Project Layout
---

# Project Layout

```
a2a-orchestrator/
├── src/a2a_orchestrator/
│   ├── common/
│   │   ├── a2a_helpers.py     # build_agent_card, discover_agents, status/text/artifact helpers
│   │   ├── claude.py          # Anthropic client, call_with_schema, stream_text
│   │   ├── logging.py         # structlog setup
│   │   ├── persistence.py     # save_recipe -> json + md
│   │   ├── ratelimit.py       # per-IP rate-limit ASGI middleware
│   │   └── recipe.py          # Pydantic Recipe model + JSON Schema
│   ├── orchestrator/
│   │   ├── __main__.py        # FastAPI parent + A2A mount
│   │   ├── executor.py        # OrchestratorExecutor
│   │   ├── planner.py         # PLAN_SCHEMA, build_plan, substitute_placeholders, synthesize
│   │   └── openai_compat.py   # /v1/chat/completions and /v1/models
│   ├── recipe_url/
│   │   ├── __main__.py
│   │   ├── executor.py
│   │   └── extract.py         # main-text extraction
│   ├── recipe_gen/
│   │   ├── __main__.py
│   │   └── executor.py
│   └── shell/
│       ├── __main__.py
│       ├── executor.py
│       └── sandbox.py         # docker-run wrapper
├── docs/
│   ├── openapi/               # static OpenAPI specs (committed)
│   └── ...                    # mkdocs source
├── k8s/                       # example manifests
├── scripts/
│   ├── build_shell_image.sh
│   ├── generate_openapi.py
│   ├── run_all.sh
│   └── verify-deployment.py
├── tests/
├── Dockerfile
├── Makefile
├── mkdocs.yml
├── pyproject.toml
├── ruff.toml
└── uv.lock
```

## Key seams

- **`OrchestratorExecutor.execute()`** — the single ASGI-agnostic place where the whole flow happens. Extending behavior usually means changing this method.
- **`planner.PLAN_SCHEMA`** — the contract between Claude and the dispatch loop. Loosening or tightening this changes what plans Claude is allowed to emit.
- **`common.a2a_helpers`** — every agent goes through these helpers for cards, discovery, and event construction. Adding a new event type starts here.
- **`common.recipe.Recipe`** — the structured artifact emitted by recipe-url and recipe-gen. Adding fields here propagates through the JSON Schema (used for tool-use), the Markdown rendering, and persistence.
