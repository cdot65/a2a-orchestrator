---
title: Configuration
---

# Configuration

All configuration is via environment variables (loaded from `.env` in development, from k8s `Secret`/`ConfigMap` in production).

## Required

| Variable | Description |
|---|---|
| `ANTHROPIC_API_KEY` | Anthropic API key. All four agents use it for Claude calls (planner, synthesizer, recipe extractors). |

## Ports

| Variable | Default | Used by |
|---|---|---|
| `ORCHESTRATOR_PORT` | `8000` | orchestrator |
| `RECIPE_URL_PORT` | `8001` | recipe-url |
| `RECIPE_GEN_PORT` | `8002` | recipe-gen |
| `SHELL_PORT` | `8003` | shell |

## Discovery

The orchestrator discovers peer agents at startup. **One** of these must be set; if both are present, `A2A_DISCOVERY_URLS` wins.

| Variable | Example | When to use |
|---|---|---|
| `A2A_DISCOVERY_PORTS` | `8001,8002,8003` | Local dev — agents reachable on `http://localhost:PORT` |
| `A2A_DISCOVERY_URLS` | `http://recipe-url.a2a.svc.cluster.local:8001,http://recipe-gen.a2a.svc.cluster.local:8002` | Kubernetes / remote — full base URLs |

The discoverer rewrites `card.url` on every fetched card to the URL it actually reached. That way subsequent `A2AClient` calls use the resolvable address rather than the `localhost:PORT` value the agent advertises in its own card.

## Model

| Variable | Default | Description |
|---|---|---|
| `CLAUDE_MODEL` | `claude-haiku-4-5-20251001` | Claude model used for planning, recipe structuring, and synthesis. |

## Logging

| Variable | Default | Values |
|---|---|---|
| `LOG_FORMAT` | `pretty` (locally), `json` (in the example k8s manifests) | `pretty` for human-readable, `json` for log shippers |

## Rate limiting

| Variable | Default | Format |
|---|---|---|
| `RATE_LIMIT` | `1200/minute` | Comma-separated `limits`-package specs, e.g. `50/minute,5/second` |

Enforced at the **outer** ASGI layer so the limit applies to both the OpenAI-compat router and the mounted A2A sub-app. See [Rate Limiting](../architecture/rate-limiting.md).

## Recipe storage

| Variable | Default | Description |
|---|---|---|
| `RECIPES_DIR` | `./recipes` | Where recipe-url and recipe-gen persist `.json` + `.md` artifacts |
| `WORKSPACE_DIR` | `./workspace` | Mounted read-only into the shell agent's sandbox as `/work` |
