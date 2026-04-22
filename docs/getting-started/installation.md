---
title: Installation
---

# Installation

## Prerequisites

| Tool | Version | Why |
|---|---|---|
| Python | 3.12+ | Project minimum |
| [`uv`](https://docs.astral.sh/uv/) | latest | Dependency + venv management |
| Docker | recent | Only for the **shell** agent's sandbox |
| `jq` | any | Pretty-printing curl output in examples |

You also need an **Anthropic API key** with access to `claude-haiku-4-5-20251001` (the default model — overridable via `CLAUDE_MODEL`).

## Clone and sync

```bash
git clone https://github.com/cdot65/a2a-orchestrator.git
cd a2a-orchestrator
uv sync
```

`uv sync` creates `.venv/` and installs runtime + dev dependencies pinned by `uv.lock`.

## Configure environment

```bash
cp .env.example .env
```

Edit `.env` and set:

```bash
ANTHROPIC_API_KEY=sk-ant-...
```

The other variables in `.env.example` have sensible defaults — see [Configuration](configuration.md) for details.

## Build the shell-agent sandbox image (optional)

The shell agent runs every command inside a fresh Docker container. If you intend to use it locally:

```bash
make shell-image
```

If you skip this, the orchestrator + the two recipe agents still work — only the shell skill will fail to dispatch.

## Verify

```bash
uv run pytest -v
```

All tests should pass with no network access required (HTTP calls to Claude and external URLs are mocked).
