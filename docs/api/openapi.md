---
title: OpenAPI Specs
---

# OpenAPI Specs

The repo ships a pre-generated OpenAPI document per agent under `docs/openapi/`. Each running agent also serves a live spec.

## Static specs

| File | Description |
|---|---|
| `docs/openapi/orchestrator.openapi.json` | Full merged spec for the orchestrator: A2A + OpenAI-compat |
| `docs/openapi/recipe-url.openapi.json` | Recipe URL parser |
| `docs/openapi/recipe-gen.openapi.json` | Recipe generator |
| `docs/openapi/shell.openapi.json` | Shell agent |
| `docs/openapi/a2a-protocol.openapi.json` | The shared A2A protocol surface (paths and schemas common to every agent) |

These are committed and used by:

- The Dockerfile, which copies `docs/openapi/` into the image so the orchestrator can serve `/openapi.json` from disk.
- `scripts/verify-deployment.py`, which validates live responses against schemas in these files.

Regenerate them with:

```bash
uv run python scripts/generate_openapi.py
```

## Live specs

| Agent | Path | Source |
|---|---|---|
| orchestrator | `/openapi.json` | Static merged file (A2A + OpenAI-compat) |
| orchestrator | `/v1/openapi.json` | FastAPI-generated, OpenAI-compat **only** |
| orchestrator | `/v1/docs` | Swagger UI for OpenAI-compat |
| recipe-url | `/openapi.json` | Static `recipe-url.openapi.json` |
| recipe-gen | `/openapi.json` | Static `recipe-gen.openapi.json` |
| shell | `/openapi.json` | Static `shell.openapi.json` |

## Why two spec files for the orchestrator?

The OpenAI-compat surface is built with FastAPI, which auto-generates an OpenAPI document from its routes (`/v1/openapi.json`). That doc only knows about `/v1/...`.

The A2A surface comes from `A2AStarletteApplication`, which is a Starlette sub-app mounted at `/`. FastAPI doesn't introspect mounted apps, so the A2A paths and types don't appear in the auto-generated spec.

To give consumers a single complete document, `scripts/generate_openapi.py` merges the FastAPI spec with the static A2A protocol spec into `docs/openapi/orchestrator.openapi.json`. The orchestrator serves that merged file at `/openapi.json` (separately from FastAPI's `/v1/openapi.json`).
