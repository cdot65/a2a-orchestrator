# A2A Recipe Orchestrator — Design

**Date:** 2026-04-20
**Status:** Approved, ready for implementation planning

## Purpose

Build an Agent-to-Agent (A2A) system using Google's A2A protocol. An orchestrator agent fields incoming requests and dispatches work to specialized agents via a planner pattern. Intended as a real, working local service exposed over HTTP for other applications to call.

## Scope

Four agents, each a separate process, each a compliant A2A server:

1. **orchestrator** (`:8000`) — planner loop; decomposes requests, dispatches to specialists, synthesizes results.
2. **recipe-url** (`:8001`) — given a URL, fetches the page, extracts a structured recipe.
3. **recipe-gen** (`:8002`) — given a freeform prompt, generates a structured recipe.
4. **shell** (`:8003`) — runs sandboxed bash commands (grep/cat/ls/find/etc.) in a read-only Docker container.

Out of scope: auth, web UI, persistent queue, retries, observability beyond structured logs, production deployment.

## Architecture

```
External A2A client ──JSON-RPC/SSE──▶ Orchestrator :8000
                                          │
                      ┌───────────────────┼───────────────────┐
                      ▼                   ▼                   ▼
                recipe-url :8001   recipe-gen :8002    shell :8003
```

- All four agents use `a2a-sdk` (Python) with SSE streaming via `tasks/sendSubscribe`.
- Each publishes its Agent Card at `/.well-known/agent-card.json` (current A2A spec path).
- **Discovery:** on startup, orchestrator probes `http://localhost:{port}/.well-known/agent-card.json` for each port in `A2A_DISCOVERY_PORTS` (default `8001,8002,8003`). Skills are cached. If an agent is unreachable, orchestrator logs a warning and continues with reduced capability.
- **Auth:** none. Agent Cards declare `authentication: none`. Local/dev only.
- **LLM:** all agents call Claude Haiku 4.5 (`claude-haiku-4-5-20251001`) via the Anthropic SDK. Shared client module in `common/claude.py`.

## Shared data model

All recipe-producing agents return the same structured shape.

```python
# src/a2a_orchestrator/common/recipe.py
class Recipe(BaseModel):
    title: str
    description: str
    ingredients: list[str]
    prep_steps: list[str]
    cooking_steps: list[str]
    chef_notes: str | None = None
    source_url: str | None = None
```

- **A2A return shape:** one `text` artifact with `mimeType: application/json` containing `Recipe.model_dump_json()`.
- **Persistence:** after a successful generation, the agent also writes `recipes/<slug>-<YYYYMMDD-HHMMSS>.json` and `recipes/<slug>-<YYYYMMDD-HHMMSS>.md` (human-readable). Slug derived from title (lowercased, non-alphanumerics replaced with `-`).
- **Output dir:** `RECIPES_DIR` env (default `$PWD/recipes`). Created on demand.
- **Validation:** Claude is prompted with the JSON schema as a forced tool call. The SDK parses the tool input into a `Recipe`.

## Per-agent design

### recipe-url (:8001)

- **Skill:** `parse_recipe_url`
  - Input: URL string.
  - Output: `Recipe` JSON (with `source_url` populated).
- **Flow:** `httpx.get(url)` → `trafilatura.extract()` to isolate main content (fallback to raw HTML text if trafilatura returns empty) → Claude Haiku with `Recipe` as a forced tool call → persist + return.
- **Streaming:** status updates `fetching` → `extracting` → `structuring` → final artifact.

### recipe-gen (:8002)

- **Skill:** `generate_recipe`
  - Input: freeform prompt (e.g., "a spicy vegan ramen for 2").
  - Output: `Recipe` JSON (`source_url` null).
- **Flow:** Claude Haiku with `Recipe` as a forced tool call → persist + return.
- **Streaming:** status updates + streams Claude's incremental output as text parts before the final artifact.

### shell (:8003)

- **Skill:** `run_shell`
  - Input: command string.
  - Output: JSON `{stdout, stderr, exit_code}`.
- **Flow:** spawn one-shot Docker container (details in Sandbox section), capture output, return.
- **Streaming:** stdout/stderr lines streamed as text parts as they arrive. Final artifact includes exit code and truncation flag if hit.

### orchestrator (:8000)

- **Skill:** `orchestrate`
  - Input: freeform user request.
  - Output: natural-language synthesis of the results.
- See "Planner loop" below.

## Planner loop (orchestrator internals)

Per incoming request:

1. **Plan call.** Claude Haiku receives the user request plus the list of discovered agents (name, description, skills, example inputs). Claude returns a plan as a forced tool call:
   ```json
   {
     "steps": [
       {"agent": "recipe-url", "skill": "parse_recipe_url", "input": "https://..."},
       {"agent": "shell", "skill": "run_shell", "input": "ls recipes/"}
     ]
   }
   ```
2. **Stream the plan** to the client as a text part ("Plan: 1) fetch URL, 2) list recipes").
3. **Execute sequentially.** For each step:
   - Open an A2A client to the target agent, call `tasks/sendSubscribe`.
   - Forward inner status updates and artifacts to the outer client as nested text parts (prefixed with `[recipe-url]`, etc.).
   - Capture the final artifact; store in a step-context dict.
   - If a step fails, stop; surface the error; no retry.
4. **Synthesis call.** Claude Haiku receives the original request plus all step outputs, produces a natural-language answer, streamed to the client.
5. Mark the outer task `completed`.

**Context passing:** the plan may reference prior steps with `{{step_1.output}}` placeholders. Orchestrator substitutes before dispatch. No re-planning, no loops, no parallelism.

**Edge cases:**
- Empty plan → synthesis-only response.
- Single-step plan → still goes through the loop (uniform handling).
- Discovery failed for an agent → Claude sees a shorter capability list; plans around it.

## Shell sandbox

One-shot Docker container per command:

```bash
docker run --rm \
  --network=none \
  --read-only \
  --tmpfs /tmp:size=64m \
  --memory=256m \
  --cpus=0.5 \
  --pids-limit=64 \
  -v "$WORKSPACE_DIR:/work:ro" \
  -w /work \
  a2a-shell:latest \
  sh -c "$COMMAND"
```

- **Image:** `a2a-shell:latest`, built from `docker/shell/Dockerfile`. Base: `alpine:3.20`. Includes `grep`, `findutils`, `ripgrep`, `jq`, `coreutils`, `busybox-extras`. No network tools, no package manager in runtime.
- **Workspace:** `WORKSPACE_DIR` env (default `$PWD/workspace`). Mounted read-only.
- **Limits:** 256MB RAM, 0.5 CPU, 64 PIDs, no network, 30s wall-clock timeout (`asyncio.wait_for` + SIGKILL on breach).
- **Output:** stdout and stderr streamed to the A2A task as they arrive. Each stream truncated at 1MB; truncation flagged in the final artifact.
- **Startup:** shell agent refuses to start if `docker info` fails. Error logged clearly.
- **Build:** `make shell-image` or `scripts/build_shell_image.sh`. Run once before starting the shell agent.

## Project structure

```
a2a-orchestrator/
├── pyproject.toml
├── uv.lock
├── ruff.toml
├── Makefile
├── README.md
├── .env.example
├── .gitignore
├── src/a2a_orchestrator/
│   ├── common/
│   │   ├── recipe.py
│   │   ├── claude.py
│   │   ├── persistence.py
│   │   └── a2a_helpers.py
│   ├── orchestrator/
│   │   ├── __main__.py
│   │   ├── executor.py
│   │   └── planner.py
│   ├── recipe_url/
│   │   ├── __main__.py
│   │   ├── executor.py
│   │   └── extract.py
│   ├── recipe_gen/
│   │   ├── __main__.py
│   │   └── executor.py
│   └── shell/
│       ├── __main__.py
│       ├── executor.py
│       └── sandbox.py
├── docker/shell/Dockerfile
├── scripts/
│   ├── run_all.sh
│   └── build_shell_image.sh
├── tests/
│   ├── common/
│   ├── orchestrator/
│   ├── recipe_url/
│   ├── recipe_gen/
│   └── shell/
├── recipes/       # gitignored
└── workspace/     # gitignored
```

## Tooling

- **Package manager:** `uv`. `uv sync`, `uv run python -m a2a_orchestrator.<agent>`.
- **Lint/format:** `ruff`. Line length 100. Default rules plus `I` (isort) and `UP` (pyupgrade).
- **Tests:** `pytest` with `pytest-asyncio` (agents are async) and `respx` (HTTP mocking).
- **Runtime deps:** `a2a-sdk`, `anthropic`, `pydantic`, `httpx`, `trafilatura`, `uvicorn`, `python-dotenv`, `structlog`.
- **Dev deps:** `pytest`, `pytest-asyncio`, `respx`, `ruff`.
- **Python:** 3.12+.

## Testing strategy

All unit-level, all mocked. No external network, no real Docker, no real Anthropic calls.

- **`tests/common/`** — Recipe schema roundtrip; persistence writes expected files; Claude helper parses forced tool-use responses correctly.
- **Per-agent executor tests:**
  - Mock `anthropic.Anthropic` to return canned tool-use responses.
  - Mock `httpx` via `respx` for recipe-url.
  - Mock `asyncio.create_subprocess_exec` for shell.
  - Assert A2A task lifecycle: `submitted → working → completed` with the expected artifact shape.
- **Orchestrator tests:**
  - Mock A2A client calls to child agents (fixtures return canned streaming events).
  - Mock Claude for plan + synthesis.
  - Verify: plan → dispatch → synthesize ordering, `{{step_N.output}}` substitution, early abort on step failure.
- **Fixtures:** `tests/fixtures/recipes/` with 2–3 raw HTML samples and expected parsed output; a sample Agent Card JSON.

## Observability

- **Logging:** `structlog`. JSON output when `LOG_FORMAT=json`, pretty otherwise. One named logger per agent. A `task_id` is bound to every log line for the duration of a task.
- **Key events:** `task_started`, `plan_generated` (orchestrator), `agent_dispatched`, `step_completed`, `step_failed`, `synthesis_done`, `task_completed`. Claude calls log the model, input tokens, output tokens, and wall-clock duration.
- **No metrics, no tracing.** Out of scope.

## Error handling

- Discovery failure on startup → warn, continue with reduced capabilities. Orchestrator logs which agents are missing.
- Child agent returns error → propagate to outer task as `failed` with the error text. No retry.
- Claude API error → same: mark outer task `failed` with clear error.
- Docker not running → shell agent exits with code 1 at startup.

## Unresolved questions

- None — all major design choices settled. If the A2A Agent Card path differs between SDK versions at implementation time, defer to what `a2a-sdk` produces and update discovery accordingly.
