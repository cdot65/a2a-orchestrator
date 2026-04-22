---
title: Testing
---

# Testing

```bash
make test
```

…runs `pytest -v` against the `tests/` directory. All tests are offline — Anthropic and outbound HTTP calls are mocked.

## Layout

| Path | Coverage |
|---|---|
| `tests/common/test_a2a_helpers.py` | Card building, status/text/artifact event helpers, discovery |
| `tests/orchestrator/test_executor.py` | Plan + dispatch + synthesis using mocked specialist agents |
| `tests/orchestrator/test_openai_compat.py` | `/v1/chat/completions` sync and SSE shape |
| `tests/orchestrator/test_ratelimit.py` | Per-IP rate-limit middleware behavior, `X-Forwarded-For` handling |
| `tests/recipe_url/...` | URL agent input validation and pipeline |
| `tests/recipe_gen/...` | Gen agent pipeline |

## Running a subset

```bash
uv run pytest tests/orchestrator -k history
uv run pytest tests/common/test_a2a_helpers.py -v
```

## Lint and format

```bash
make lint   # ruff check
make fmt    # ruff format + ruff check --fix
```

`ruff.toml` is the single source of truth for lint config.

## Verifying a deployed instance

`scripts/verify-deployment.py` runs schema-validated checks against a live orchestrator. Useful after a deploy:

```bash
uv run python scripts/verify-deployment.py https://your-host
```

It sends real A2A and OpenAI-compat requests and validates responses against the OpenAPI specs under `docs/openapi/`.
