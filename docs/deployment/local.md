---
title: Local Deployment
---

# Local Deployment

## All-in-one

```bash
make run-all
```

This runs `scripts/run_all.sh`, which starts all four agents in the foreground in a single terminal. Logs are interleaved. `Ctrl-C` stops everything.

## Per-agent

You can also run agents individually in separate terminals — useful when iterating on one of them:

```bash
uv run python -m a2a_orchestrator.recipe_url
uv run python -m a2a_orchestrator.recipe_gen
uv run python -m a2a_orchestrator.shell
uv run python -m a2a_orchestrator.orchestrator
```

The orchestrator must be started **last** so its discovery succeeds. (Or restart it after any peer comes up — discovery runs per-task, not at process start.)

## Skipping the shell agent

The shell agent requires Docker and the sandbox image (`make shell-image`). If you don't need it locally:

```bash
A2A_DISCOVERY_PORTS=8001,8002 make run-all
```

…and only start the URL + gen agents alongside the orchestrator. The planner sees a smaller capability set and won't try to dispatch to `shell`.

## Logs

Default log format is `pretty` (human-readable structlog output). Switch to JSON for log shippers:

```bash
LOG_FORMAT=json make run-all
```
