# A2A Recipe Orchestrator Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build four A2A-compliant Python agents (orchestrator, recipe-url, recipe-gen, shell) running as separate processes on localhost; orchestrator auto-discovers the others, plans via Claude, dispatches sequentially, and synthesizes results.

**Architecture:** Single-package monorepo, one venv (uv). Each agent is an `a2a-sdk` server with SSE streaming, its own `AgentExecutor`, and its own port. Recipe agents call Claude Haiku 4.5 with a forced tool call to return structured `Recipe` objects. Shell agent runs commands in a one-shot read-only Docker container. Orchestrator runs a plan → dispatch-loop → synthesize flow.

**Tech Stack:** Python 3.12, uv, ruff, pytest + pytest-asyncio + respx, a2a-sdk, anthropic SDK, pydantic, httpx, trafilatura, structlog, uvicorn, Docker (for shell sandbox).

**Spec:** [docs/superpowers/specs/2026-04-20-a2a-orchestrator-design.md](../specs/2026-04-20-a2a-orchestrator-design.md)

**A2A SDK note:** The `a2a-sdk` Python package API may evolve between versions. Code blocks in this plan follow the current public API (`AgentExecutor`, `RequestContext`, `EventQueue`, `AgentCard`, `AgentSkill`, `Message`, `TextPart`, `Artifact`, `TaskStatusUpdateEvent`). If a symbol is not found, consult the installed SDK and adjust imports — the shape of the executor contract (`execute(context, event_queue)`) is stable.

---

## File Structure

**Created:**
- `pyproject.toml`, `uv.lock`, `ruff.toml`, `Makefile`, `README.md`, `.env.example`, `.gitignore`
- `src/a2a_orchestrator/__init__.py`
- `src/a2a_orchestrator/common/{__init__,recipe,claude,persistence,a2a_helpers,logging}.py`
- `src/a2a_orchestrator/orchestrator/{__init__,__main__,executor,planner}.py`
- `src/a2a_orchestrator/recipe_url/{__init__,__main__,executor,extract}.py`
- `src/a2a_orchestrator/recipe_gen/{__init__,__main__,executor}.py`
- `src/a2a_orchestrator/shell/{__init__,__main__,executor,sandbox}.py`
- `docker/shell/Dockerfile`
- `scripts/run_all.sh`, `scripts/build_shell_image.sh`
- `tests/…` mirroring `src/a2a_orchestrator/` layout
- `tests/fixtures/recipes/sample.html`, `tests/fixtures/recipes/sample_expected.json`
- `tests/fixtures/agent_cards/recipe_url.json`

**Runtime (gitignored):**
- `recipes/` — output directory for persisted recipes
- `workspace/` — read-only mount for shell agent

---

## Task 1: Project scaffold

**Files:**
- Create: `pyproject.toml`, `ruff.toml`, `Makefile`, `.env.example`, `.gitignore`
- Create: `src/a2a_orchestrator/__init__.py` and all subpackage `__init__.py` files (empty)
- Create: `tests/__init__.py` and `tests/conftest.py`

- [ ] **Step 1: Write `pyproject.toml`**

```toml
[project]
name = "a2a-orchestrator"
version = "0.1.0"
description = "A2A orchestrator with specialist agents for recipes and shell"
requires-python = ">=3.12"
dependencies = [
  "a2a-sdk>=0.2",
  "anthropic>=0.40",
  "pydantic>=2.7",
  "httpx>=0.27",
  "trafilatura>=1.12",
  "uvicorn>=0.30",
  "python-dotenv>=1.0",
  "structlog>=24.1",
]

[dependency-groups]
dev = [
  "pytest>=8",
  "pytest-asyncio>=0.23",
  "respx>=0.21",
  "ruff>=0.6",
]

[tool.pytest.ini_options]
asyncio_mode = "auto"
testpaths = ["tests"]

[build-system]
requires = ["hatchling"]
build-backend = "hatchling.build"

[tool.hatch.build.targets.wheel]
packages = ["src/a2a_orchestrator"]
```

- [ ] **Step 2: Write `ruff.toml`**

```toml
line-length = 100
target-version = "py312"

[lint]
select = ["E", "F", "I", "UP", "B", "W"]
```

- [ ] **Step 3: Write `.env.example`**

```bash
ANTHROPIC_API_KEY=sk-ant-...
CLAUDE_MODEL=claude-haiku-4-5-20251001

ORCHESTRATOR_PORT=8000
RECIPE_URL_PORT=8001
RECIPE_GEN_PORT=8002
SHELL_PORT=8003

A2A_DISCOVERY_PORTS=8001,8002,8003

RECIPES_DIR=./recipes
WORKSPACE_DIR=./workspace

LOG_FORMAT=pretty
```

- [ ] **Step 4: Write `.gitignore`**

```gitignore
.venv/
__pycache__/
*.pyc
.pytest_cache/
.ruff_cache/
.env
recipes/
workspace/
dist/
*.egg-info/
```

- [ ] **Step 5: Write `Makefile`**

```makefile
.PHONY: install lint fmt test shell-image run-all clean

install:
	uv sync

lint:
	uv run ruff check .

fmt:
	uv run ruff format .
	uv run ruff check --fix .

test:
	uv run pytest -v

shell-image:
	./scripts/build_shell_image.sh

run-all:
	./scripts/run_all.sh

clean:
	rm -rf .pytest_cache .ruff_cache dist *.egg-info
```

- [ ] **Step 6: Create package skeleton files**

Create these empty files (all are `__init__.py` unless noted):

```bash
mkdir -p src/a2a_orchestrator/{common,orchestrator,recipe_url,recipe_gen,shell}
mkdir -p tests/{common,orchestrator,recipe_url,recipe_gen,shell,fixtures/recipes,fixtures/agent_cards}
mkdir -p scripts docker/shell

touch src/a2a_orchestrator/__init__.py
touch src/a2a_orchestrator/common/__init__.py
touch src/a2a_orchestrator/orchestrator/__init__.py
touch src/a2a_orchestrator/recipe_url/__init__.py
touch src/a2a_orchestrator/recipe_gen/__init__.py
touch src/a2a_orchestrator/shell/__init__.py
touch tests/__init__.py
touch tests/common/__init__.py
touch tests/orchestrator/__init__.py
touch tests/recipe_url/__init__.py
touch tests/recipe_gen/__init__.py
touch tests/shell/__init__.py
```

- [ ] **Step 7: Write `tests/conftest.py`**

```python
import os
import pytest


@pytest.fixture(autouse=True)
def _env(monkeypatch, tmp_path):
    monkeypatch.setenv("ANTHROPIC_API_KEY", "test-key")
    monkeypatch.setenv("CLAUDE_MODEL", "claude-haiku-4-5-20251001")
    monkeypatch.setenv("RECIPES_DIR", str(tmp_path / "recipes"))
    monkeypatch.setenv("WORKSPACE_DIR", str(tmp_path / "workspace"))
    (tmp_path / "recipes").mkdir()
    (tmp_path / "workspace").mkdir()
    yield
```

- [ ] **Step 8: Run `uv sync` and confirm**

Run: `uv sync`
Expected: creates `.venv/`, resolves deps, writes `uv.lock`. Exit 0.

- [ ] **Step 9: Run the test suite**

Run: `uv run pytest -v`
Expected: "no tests ran" (exit 5). That's fine — we have no tests yet.

- [ ] **Step 10: Run ruff**

Run: `uv run ruff check .`
Expected: All checks passed.

- [ ] **Step 11: Commit**

```bash
git add -A
git commit -m "scaffold: project skeleton with uv, ruff, pytest"
```

---

## Task 2: Recipe data model

**Files:**
- Create: `src/a2a_orchestrator/common/recipe.py`
- Test: `tests/common/test_recipe.py`

- [ ] **Step 1: Write the failing test**

`tests/common/test_recipe.py`:

```python
import json

import pytest
from pydantic import ValidationError

from a2a_orchestrator.common.recipe import Recipe, recipe_json_schema, slugify


def _sample_payload() -> dict:
    return {
        "title": "Spicy Vegan Ramen",
        "description": "A warming bowl of chili-infused ramen.",
        "ingredients": ["200g ramen noodles", "1 tbsp chili oil"],
        "prep_steps": ["Boil water", "Slice scallions"],
        "cooking_steps": ["Cook noodles for 3 min", "Add chili oil"],
        "chef_notes": "Add mushrooms for umami.",
        "source_url": "https://example.com/ramen",
    }


def test_recipe_roundtrip():
    recipe = Recipe(**_sample_payload())
    assert recipe.title == "Spicy Vegan Ramen"
    assert recipe.source_url == "https://example.com/ramen"
    data = json.loads(recipe.model_dump_json())
    assert data["ingredients"] == ["200g ramen noodles", "1 tbsp chili oil"]


def test_recipe_optional_fields_default_none():
    payload = _sample_payload()
    del payload["chef_notes"]
    del payload["source_url"]
    recipe = Recipe(**payload)
    assert recipe.chef_notes is None
    assert recipe.source_url is None


def test_recipe_rejects_missing_title():
    payload = _sample_payload()
    del payload["title"]
    with pytest.raises(ValidationError):
        Recipe(**payload)


def test_recipe_json_schema_has_expected_properties():
    schema = recipe_json_schema()
    assert schema["type"] == "object"
    assert "title" in schema["properties"]
    assert "ingredients" in schema["required"]


@pytest.mark.parametrize(
    "title,expected",
    [
        ("Spicy Vegan Ramen", "spicy-vegan-ramen"),
        ("Mom's Best Cookies!", "mom-s-best-cookies"),
        ("  weird   spacing ", "weird-spacing"),
    ],
)
def test_slugify(title, expected):
    assert slugify(title) == expected
```

- [ ] **Step 2: Run the test to verify it fails**

Run: `uv run pytest tests/common/test_recipe.py -v`
Expected: `ImportError` — module doesn't exist yet.

- [ ] **Step 3: Implement `Recipe` and helpers**

`src/a2a_orchestrator/common/recipe.py`:

```python
import re

from pydantic import BaseModel, Field


class Recipe(BaseModel):
    title: str
    description: str
    ingredients: list[str] = Field(min_length=1)
    prep_steps: list[str]
    cooking_steps: list[str]
    chef_notes: str | None = None
    source_url: str | None = None


def recipe_json_schema() -> dict:
    """JSON schema for forced tool-use with Claude."""
    return Recipe.model_json_schema()


_SLUG_RE = re.compile(r"[^a-z0-9]+")


def slugify(title: str) -> str:
    lower = title.lower().strip()
    return _SLUG_RE.sub("-", lower).strip("-")
```

- [ ] **Step 4: Run the test to verify it passes**

Run: `uv run pytest tests/common/test_recipe.py -v`
Expected: all 6 tests PASS.

- [ ] **Step 5: Commit**

```bash
git add src/a2a_orchestrator/common/recipe.py tests/common/test_recipe.py
git commit -m "feat(common): recipe model and slugify"
```

---

## Task 3: Persistence

**Files:**
- Create: `src/a2a_orchestrator/common/persistence.py`
- Test: `tests/common/test_persistence.py`

- [ ] **Step 1: Write the failing test**

`tests/common/test_persistence.py`:

```python
import json
import os
from pathlib import Path

from a2a_orchestrator.common.persistence import save_recipe
from a2a_orchestrator.common.recipe import Recipe


def _sample_recipe() -> Recipe:
    return Recipe(
        title="Spicy Vegan Ramen",
        description="A warming bowl.",
        ingredients=["noodles", "chili oil"],
        prep_steps=["boil water"],
        cooking_steps=["cook 3 min"],
        chef_notes="Add mushrooms.",
        source_url="https://example.com/ramen",
    )


def test_save_recipe_writes_json_and_md(tmp_path, monkeypatch):
    monkeypatch.setenv("RECIPES_DIR", str(tmp_path))
    paths = save_recipe(_sample_recipe())

    assert paths.json_path.exists()
    assert paths.md_path.exists()
    assert paths.json_path.parent == tmp_path

    data = json.loads(paths.json_path.read_text())
    assert data["title"] == "Spicy Vegan Ramen"

    md = paths.md_path.read_text()
    assert "# Spicy Vegan Ramen" in md
    assert "## Ingredients" in md
    assert "- noodles" in md
    assert "## Chef Notes" in md


def test_save_recipe_omits_chef_notes_section_when_none(tmp_path, monkeypatch):
    monkeypatch.setenv("RECIPES_DIR", str(tmp_path))
    recipe = _sample_recipe().model_copy(update={"chef_notes": None})
    paths = save_recipe(recipe)
    md = paths.md_path.read_text()
    assert "## Chef Notes" not in md


def test_save_recipe_filenames_use_slug_and_timestamp(tmp_path, monkeypatch):
    monkeypatch.setenv("RECIPES_DIR", str(tmp_path))
    paths = save_recipe(_sample_recipe())
    name = paths.json_path.name
    assert name.startswith("spicy-vegan-ramen-")
    assert name.endswith(".json")
    # timestamp portion is 15 chars: YYYYMMDD-HHMMSS
    stem = paths.json_path.stem
    assert len(stem.split("-")[-2]) == 8  # date
    assert len(stem.split("-")[-1]) == 6  # time


def test_save_recipe_creates_dir_if_missing(tmp_path, monkeypatch):
    out = tmp_path / "does-not-exist-yet"
    monkeypatch.setenv("RECIPES_DIR", str(out))
    paths = save_recipe(_sample_recipe())
    assert out.is_dir()
    assert paths.json_path.exists()
```

- [ ] **Step 2: Run the test to verify it fails**

Run: `uv run pytest tests/common/test_persistence.py -v`
Expected: `ImportError`.

- [ ] **Step 3: Implement persistence**

`src/a2a_orchestrator/common/persistence.py`:

```python
import os
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path

from a2a_orchestrator.common.recipe import Recipe, slugify


@dataclass(frozen=True)
class SavedPaths:
    json_path: Path
    md_path: Path


def _recipes_dir() -> Path:
    return Path(os.environ.get("RECIPES_DIR", "./recipes"))


def _render_markdown(recipe: Recipe) -> str:
    parts = [f"# {recipe.title}", "", recipe.description, ""]
    if recipe.source_url:
        parts += [f"Source: {recipe.source_url}", ""]

    parts += ["## Ingredients", ""]
    parts += [f"- {i}" for i in recipe.ingredients]

    parts += ["", "## Prep Steps", ""]
    parts += [f"{n}. {s}" for n, s in enumerate(recipe.prep_steps, 1)]

    parts += ["", "## Cooking Steps", ""]
    parts += [f"{n}. {s}" for n, s in enumerate(recipe.cooking_steps, 1)]

    if recipe.chef_notes:
        parts += ["", "## Chef Notes", "", recipe.chef_notes]

    parts.append("")
    return "\n".join(parts)


def save_recipe(recipe: Recipe) -> SavedPaths:
    out_dir = _recipes_dir()
    out_dir.mkdir(parents=True, exist_ok=True)

    slug = slugify(recipe.title) or "recipe"
    stamp = datetime.now().strftime("%Y%m%d-%H%M%S")
    base = f"{slug}-{stamp}"

    json_path = out_dir / f"{base}.json"
    md_path = out_dir / f"{base}.md"

    json_path.write_text(recipe.model_dump_json(indent=2))
    md_path.write_text(_render_markdown(recipe))

    return SavedPaths(json_path=json_path, md_path=md_path)
```

- [ ] **Step 4: Run the test to verify it passes**

Run: `uv run pytest tests/common/test_persistence.py -v`
Expected: 4 tests PASS.

- [ ] **Step 5: Commit**

```bash
git add src/a2a_orchestrator/common/persistence.py tests/common/test_persistence.py
git commit -m "feat(common): persist recipe as json and markdown"
```

---

## Task 4: Shared Claude helper (structured output)

**Files:**
- Create: `src/a2a_orchestrator/common/claude.py`
- Test: `tests/common/test_claude.py`

- [ ] **Step 1: Write the failing test**

`tests/common/test_claude.py`:

```python
from unittest.mock import MagicMock

import pytest

from a2a_orchestrator.common.claude import call_with_schema, stream_text


def _fake_tool_response(tool_name: str, tool_input: dict) -> MagicMock:
    block = MagicMock()
    block.type = "tool_use"
    block.name = tool_name
    block.input = tool_input
    msg = MagicMock()
    msg.content = [block]
    return msg


def test_call_with_schema_returns_tool_input(monkeypatch):
    client = MagicMock()
    client.messages.create.return_value = _fake_tool_response(
        "emit_result", {"title": "t", "n": 1}
    )

    result = call_with_schema(
        client,
        system="you structure data",
        user="make a result",
        tool_name="emit_result",
        tool_description="emit the structured result",
        schema={"type": "object", "properties": {"title": {"type": "string"}}},
    )

    assert result == {"title": "t", "n": 1}

    kwargs = client.messages.create.call_args.kwargs
    assert kwargs["model"] == "claude-haiku-4-5-20251001"
    assert kwargs["tool_choice"] == {"type": "tool", "name": "emit_result"}
    assert kwargs["tools"][0]["name"] == "emit_result"


def test_call_with_schema_raises_on_missing_tool_use():
    client = MagicMock()
    empty = MagicMock()
    empty.content = []
    client.messages.create.return_value = empty

    with pytest.raises(RuntimeError, match="no tool_use"):
        call_with_schema(
            client,
            system="s",
            user="u",
            tool_name="t",
            tool_description="d",
            schema={"type": "object"},
        )


async def test_stream_text_yields_chunks(monkeypatch):
    # Build a fake streaming context manager
    class _FakeStream:
        def __init__(self):
            self.text_stream = self._iter()

        async def _iter(self):
            for c in ["Hello ", "world"]:
                yield c

        async def __aenter__(self):
            return self

        async def __aexit__(self, *exc):
            return False

    client = MagicMock()
    client.messages.stream.return_value = _FakeStream()

    chunks = []
    async for c in stream_text(client, system="s", user="u"):
        chunks.append(c)
    assert chunks == ["Hello ", "world"]
```

- [ ] **Step 2: Run the test to verify it fails**

Run: `uv run pytest tests/common/test_claude.py -v`
Expected: `ImportError`.

- [ ] **Step 3: Implement the Claude helper**

`src/a2a_orchestrator/common/claude.py`:

```python
import os
from typing import AsyncIterator

from anthropic import Anthropic, AsyncAnthropic

_DEFAULT_MAX_TOKENS = 2048


def get_client() -> Anthropic:
    return Anthropic()


def get_async_client() -> AsyncAnthropic:
    return AsyncAnthropic()


def _model() -> str:
    return os.environ.get("CLAUDE_MODEL", "claude-haiku-4-5-20251001")


def call_with_schema(
    client: Anthropic,
    *,
    system: str,
    user: str,
    tool_name: str,
    tool_description: str,
    schema: dict,
    max_tokens: int = _DEFAULT_MAX_TOKENS,
) -> dict:
    """One-shot Claude call with a forced tool. Returns the tool input dict."""
    msg = client.messages.create(
        model=_model(),
        max_tokens=max_tokens,
        system=system,
        messages=[{"role": "user", "content": user}],
        tools=[{
            "name": tool_name,
            "description": tool_description,
            "input_schema": schema,
        }],
        tool_choice={"type": "tool", "name": tool_name},
    )
    for block in msg.content:
        if getattr(block, "type", None) == "tool_use" and block.name == tool_name:
            return dict(block.input)
    raise RuntimeError(f"Claude response had no tool_use for {tool_name!r}")


async def stream_text(
    client: AsyncAnthropic,
    *,
    system: str,
    user: str,
    max_tokens: int = _DEFAULT_MAX_TOKENS,
) -> AsyncIterator[str]:
    """Stream plain text output from Claude."""
    async with client.messages.stream(
        model=_model(),
        max_tokens=max_tokens,
        system=system,
        messages=[{"role": "user", "content": user}],
    ) as stream:
        async for chunk in stream.text_stream:
            yield chunk
```

- [ ] **Step 4: Run the test to verify it passes**

Run: `uv run pytest tests/common/test_claude.py -v`
Expected: 3 tests PASS.

- [ ] **Step 5: Commit**

```bash
git add src/a2a_orchestrator/common/claude.py tests/common/test_claude.py
git commit -m "feat(common): claude helper with forced tool use and streaming"
```

---

## Task 5: A2A helpers — Agent Card builder + discovery

**Files:**
- Create: `src/a2a_orchestrator/common/a2a_helpers.py`
- Test: `tests/common/test_a2a_helpers.py`
- Create: `tests/fixtures/agent_cards/recipe_url.json`

- [ ] **Step 1: Create the fixture Agent Card**

`tests/fixtures/agent_cards/recipe_url.json`:

```json
{
  "name": "recipe-url",
  "description": "Parse a recipe from a URL.",
  "url": "http://localhost:8001",
  "version": "0.1.0",
  "capabilities": {"streaming": true},
  "authentication": {"schemes": ["none"]},
  "skills": [
    {
      "id": "parse_recipe_url",
      "name": "parse_recipe_url",
      "description": "Fetch a URL and return a structured recipe.",
      "tags": ["recipe"],
      "examples": ["https://example.com/ramen"]
    }
  ],
  "defaultInputModes": ["text"],
  "defaultOutputModes": ["text"]
}
```

- [ ] **Step 2: Write the failing test**

`tests/common/test_a2a_helpers.py`:

```python
from pathlib import Path

import httpx
import pytest
import respx

from a2a_orchestrator.common.a2a_helpers import (
    build_agent_card,
    discover_agents,
)


FIXTURES = Path(__file__).parent.parent / "fixtures" / "agent_cards"


def test_build_agent_card_has_expected_shape():
    card = build_agent_card(
        name="recipe-gen",
        description="Generate a recipe.",
        url="http://localhost:8002",
        skills=[
            {
                "id": "generate_recipe",
                "name": "generate_recipe",
                "description": "Generate a new recipe.",
                "tags": ["recipe"],
                "examples": ["a vegan soup"],
            }
        ],
    )
    assert card["name"] == "recipe-gen"
    assert card["url"] == "http://localhost:8002"
    assert card["capabilities"]["streaming"] is True
    assert card["authentication"]["schemes"] == ["none"]
    assert card["skills"][0]["id"] == "generate_recipe"


@respx.mock
async def test_discover_agents_returns_reachable_cards():
    sample = (FIXTURES / "recipe_url.json").read_text()
    respx.get("http://localhost:8001/.well-known/agent-card.json").mock(
        return_value=httpx.Response(200, text=sample)
    )
    respx.get("http://localhost:8002/.well-known/agent-card.json").mock(
        return_value=httpx.Response(500)
    )

    cards = await discover_agents([8001, 8002])

    assert len(cards) == 1
    assert cards[0]["name"] == "recipe-url"


@respx.mock
async def test_discover_agents_skips_connection_errors():
    respx.get("http://localhost:9999/.well-known/agent-card.json").mock(
        side_effect=httpx.ConnectError("boom")
    )

    cards = await discover_agents([9999])
    assert cards == []
```

- [ ] **Step 3: Run the test to verify it fails**

Run: `uv run pytest tests/common/test_a2a_helpers.py -v`
Expected: `ImportError`.

- [ ] **Step 4: Implement the helpers**

`src/a2a_orchestrator/common/a2a_helpers.py`:

```python
import asyncio
import logging
from typing import Any

import httpx

log = logging.getLogger(__name__)

AGENT_CARD_PATH = "/.well-known/agent-card.json"


def build_agent_card(
    *,
    name: str,
    description: str,
    url: str,
    skills: list[dict[str, Any]],
    version: str = "0.1.0",
) -> dict[str, Any]:
    return {
        "name": name,
        "description": description,
        "url": url,
        "version": version,
        "capabilities": {"streaming": True},
        "authentication": {"schemes": ["none"]},
        "defaultInputModes": ["text"],
        "defaultOutputModes": ["text"],
        "skills": skills,
    }


async def _fetch_card(client: httpx.AsyncClient, port: int) -> dict[str, Any] | None:
    url = f"http://localhost:{port}{AGENT_CARD_PATH}"
    try:
        resp = await client.get(url, timeout=2.0)
    except httpx.HTTPError as e:
        log.warning("discovery failed for port %d: %s", port, e)
        return None
    if resp.status_code != 200:
        log.warning("discovery non-200 for port %d: %s", port, resp.status_code)
        return None
    try:
        return resp.json()
    except ValueError:
        log.warning("discovery: port %d returned non-JSON", port)
        return None


async def discover_agents(ports: list[int]) -> list[dict[str, Any]]:
    async with httpx.AsyncClient() as client:
        results = await asyncio.gather(*(_fetch_card(client, p) for p in ports))
    return [c for c in results if c is not None]
```

- [ ] **Step 5: Run the test to verify it passes**

Run: `uv run pytest tests/common/test_a2a_helpers.py -v`
Expected: 3 tests PASS.

- [ ] **Step 6: Commit**

```bash
git add src/a2a_orchestrator/common/a2a_helpers.py tests/common/test_a2a_helpers.py tests/fixtures/agent_cards/recipe_url.json
git commit -m "feat(common): agent card builder and discovery"
```

---

## Task 6: Structured logging setup

**Files:**
- Create: `src/a2a_orchestrator/common/logging.py`
- Test: `tests/common/test_logging.py`

- [ ] **Step 1: Write the failing test**

`tests/common/test_logging.py`:

```python
import json
import logging

from a2a_orchestrator.common.logging import configure_logging, get_logger


def test_configure_logging_pretty_smoke(monkeypatch, capsys):
    monkeypatch.setenv("LOG_FORMAT", "pretty")
    configure_logging(agent_name="test-agent")
    log = get_logger("test-agent")
    log.info("hello", task_id="abc")
    out = capsys.readouterr().out
    assert "hello" in out


def test_configure_logging_json(monkeypatch, capsys):
    monkeypatch.setenv("LOG_FORMAT", "json")
    configure_logging(agent_name="test-agent")
    log = get_logger("test-agent")
    log.info("hello", task_id="abc", count=3)
    line = capsys.readouterr().out.strip().splitlines()[-1]
    data = json.loads(line)
    assert data["event"] == "hello"
    assert data["task_id"] == "abc"
    assert data["count"] == 3
    assert data["agent"] == "test-agent"
```

- [ ] **Step 2: Run the test to verify it fails**

Run: `uv run pytest tests/common/test_logging.py -v`
Expected: `ImportError`.

- [ ] **Step 3: Implement logging**

`src/a2a_orchestrator/common/logging.py`:

```python
import logging
import os
import sys

import structlog


def configure_logging(*, agent_name: str) -> None:
    fmt = os.environ.get("LOG_FORMAT", "pretty").lower()
    logging.basicConfig(
        format="%(message)s",
        stream=sys.stdout,
        level=logging.INFO,
        force=True,
    )

    processors = [
        structlog.contextvars.merge_contextvars,
        structlog.processors.add_log_level,
        structlog.processors.TimeStamper(fmt="iso"),
        structlog.processors.CallsiteParameterAdder(
            {structlog.processors.CallsiteParameter.MODULE}
        ),
        _inject_agent(agent_name),
    ]
    if fmt == "json":
        processors.append(structlog.processors.JSONRenderer())
    else:
        processors.append(structlog.dev.ConsoleRenderer(colors=False))

    structlog.configure(
        processors=processors,
        wrapper_class=structlog.make_filtering_bound_logger(logging.INFO),
        logger_factory=structlog.PrintLoggerFactory(),
        cache_logger_on_first_use=True,
    )


def _inject_agent(name: str):
    def _p(_logger, _method, event_dict):
        event_dict["agent"] = name
        return event_dict

    return _p


def get_logger(name: str) -> structlog.stdlib.BoundLogger:
    return structlog.get_logger(name)
```

- [ ] **Step 4: Run the test to verify it passes**

Run: `uv run pytest tests/common/test_logging.py -v`
Expected: 2 tests PASS.

- [ ] **Step 5: Commit**

```bash
git add src/a2a_orchestrator/common/logging.py tests/common/test_logging.py
git commit -m "feat(common): structured logging with structlog"
```

---

## Task 7: recipe-gen agent — executor + main

**Files:**
- Create: `src/a2a_orchestrator/recipe_gen/executor.py`
- Create: `src/a2a_orchestrator/recipe_gen/__main__.py`
- Test: `tests/recipe_gen/test_executor.py`

- [ ] **Step 1: Write the failing test**

`tests/recipe_gen/test_executor.py`:

```python
import json
from unittest.mock import MagicMock, patch

import pytest

from a2a_orchestrator.recipe_gen.executor import RecipeGenExecutor, build_card


def _recipe_payload():
    return {
        "title": "Spicy Vegan Ramen",
        "description": "A warming bowl.",
        "ingredients": ["noodles", "chili oil"],
        "prep_steps": ["boil water"],
        "cooking_steps": ["cook 3 min"],
        "chef_notes": None,
        "source_url": None,
    }


class _FakeQueue:
    def __init__(self):
        self.events = []

    async def enqueue_event(self, event):
        self.events.append(event)


class _FakeContext:
    def __init__(self, user_text: str):
        self.task_id = "task-123"
        self.context_id = "ctx-1"
        self._user_text = user_text

    def get_user_input(self) -> str:
        return self._user_text


def test_build_card_reports_generate_skill():
    card = build_card("http://localhost:8002")
    assert card["name"] == "recipe-gen"
    assert card["skills"][0]["id"] == "generate_recipe"


async def test_executor_generates_and_persists_recipe(monkeypatch):
    queue = _FakeQueue()
    ctx = _FakeContext("A spicy vegan ramen for 2")

    payload = _recipe_payload()

    with patch(
        "a2a_orchestrator.recipe_gen.executor.call_with_schema",
        return_value=payload,
    ) as claude_mock, patch(
        "a2a_orchestrator.recipe_gen.executor.get_client"
    ) as client_mock:
        client_mock.return_value = MagicMock()
        executor = RecipeGenExecutor()
        await executor.execute(ctx, queue)

    claude_mock.assert_called_once()
    assert any("working" in str(e).lower() or "status" in str(e).lower() for e in queue.events)

    artifact_events = [e for e in queue.events if getattr(e, "kind", "") == "artifact"]
    assert artifact_events, "expected at least one artifact event"

    import os
    from pathlib import Path
    recipes_dir = Path(os.environ["RECIPES_DIR"])
    files = list(recipes_dir.glob("spicy-vegan-ramen-*.json"))
    assert len(files) == 1
    data = json.loads(files[0].read_text())
    assert data["title"] == "Spicy Vegan Ramen"


async def test_executor_fails_task_on_claude_error():
    queue = _FakeQueue()
    ctx = _FakeContext("A recipe")

    with patch(
        "a2a_orchestrator.recipe_gen.executor.call_with_schema",
        side_effect=RuntimeError("boom"),
    ), patch("a2a_orchestrator.recipe_gen.executor.get_client"):
        executor = RecipeGenExecutor()
        await executor.execute(ctx, queue)

    statuses = [getattr(e, "state", None) for e in queue.events]
    assert any(s == "failed" for s in statuses)
```

- [ ] **Step 2: Run the test to verify it fails**

Run: `uv run pytest tests/recipe_gen/test_executor.py -v`
Expected: `ImportError`.

- [ ] **Step 3: Implement the executor**

`src/a2a_orchestrator/recipe_gen/executor.py`:

```python
from dataclasses import dataclass
from typing import Any

from pydantic import ValidationError

from a2a_orchestrator.common.claude import call_with_schema, get_client
from a2a_orchestrator.common.logging import get_logger
from a2a_orchestrator.common.persistence import save_recipe
from a2a_orchestrator.common.recipe import Recipe, recipe_json_schema

log = get_logger("recipe-gen")


@dataclass
class _StatusEvent:
    kind: str  # "status"
    state: str  # "working" | "completed" | "failed"
    message: str = ""


@dataclass
class _ArtifactEvent:
    kind: str  # "artifact"
    mime_type: str
    text: str


SYSTEM_PROMPT = (
    "You are a recipe generator. Given a prompt, return a complete, realistic recipe "
    "using the emit_recipe tool. Fill all fields; prep_steps and cooking_steps must be "
    "ordered and self-contained. Leave source_url null."
)


def build_card(url: str) -> dict[str, Any]:
    from a2a_orchestrator.common.a2a_helpers import build_agent_card

    return build_agent_card(
        name="recipe-gen",
        description="Generate a new structured recipe from a freeform prompt.",
        url=url,
        skills=[
            {
                "id": "generate_recipe",
                "name": "generate_recipe",
                "description": "Generate a structured recipe from a natural-language prompt.",
                "tags": ["recipe", "generation"],
                "examples": [
                    "a spicy vegan ramen for 2",
                    "a chocolate chip cookie recipe that uses browned butter",
                ],
            }
        ],
    )


class RecipeGenExecutor:
    """A2A executor. Implements `execute(context, event_queue)` and `cancel(...)`."""

    async def execute(self, context, event_queue) -> None:
        user_text = context.get_user_input()
        log.info("task_started", task_id=context.task_id, prompt=user_text[:120])
        await event_queue.enqueue_event(_StatusEvent("status", "working", "generating recipe"))

        try:
            client = get_client()
            raw = call_with_schema(
                client,
                system=SYSTEM_PROMPT,
                user=user_text,
                tool_name="emit_recipe",
                tool_description="Emit the structured recipe.",
                schema=recipe_json_schema(),
            )
            recipe = Recipe(**raw)
            paths = save_recipe(recipe)
            log.info(
                "recipe_saved",
                task_id=context.task_id,
                json=str(paths.json_path),
                md=str(paths.md_path),
            )

            await event_queue.enqueue_event(
                _ArtifactEvent("artifact", "application/json", recipe.model_dump_json())
            )
            await event_queue.enqueue_event(_StatusEvent("status", "completed"))
            log.info("task_completed", task_id=context.task_id)

        except (ValidationError, RuntimeError, Exception) as exc:  # noqa: BLE001
            log.exception("task_failed", task_id=context.task_id)
            await event_queue.enqueue_event(_StatusEvent("status", "failed", str(exc)))

    async def cancel(self, context, event_queue) -> None:
        log.info("task_cancelled", task_id=getattr(context, "task_id", "?"))
```

- [ ] **Step 4: Run the test to verify it passes**

Run: `uv run pytest tests/recipe_gen/test_executor.py -v`
Expected: 3 tests PASS.

- [ ] **Step 5: Write the `__main__` entrypoint**

`src/a2a_orchestrator/recipe_gen/__main__.py`:

```python
import os

import uvicorn

from a2a_orchestrator.common.logging import configure_logging
from a2a_orchestrator.recipe_gen.executor import RecipeGenExecutor, build_card


def main() -> None:
    configure_logging(agent_name="recipe-gen")
    port = int(os.environ.get("RECIPE_GEN_PORT", "8002"))
    url = f"http://localhost:{port}"
    card = build_card(url)

    # Build A2A app from executor + card. The a2a-sdk exposes
    # either an ASGI-factory or a class; adjust import to match
    # the installed SDK.
    try:
        from a2a.server.apps import A2AStarletteApplication
        from a2a.server.request_handlers import DefaultRequestHandler
        from a2a.server.tasks import InMemoryTaskStore

        handler = DefaultRequestHandler(
            agent_executor=RecipeGenExecutor(),
            task_store=InMemoryTaskStore(),
        )
        app = A2AStarletteApplication(agent_card=card, http_handler=handler).build()
    except ImportError:
        # Fallback shape — newer SDK may expose `A2AFastAPIApplication`.
        from a2a.server.apps import A2AFastAPIApplication  # type: ignore

        app = A2AFastAPIApplication(
            agent_card=card,
            agent_executor=RecipeGenExecutor(),
        ).build()

    uvicorn.run(app, host="0.0.0.0", port=port)


if __name__ == "__main__":
    main()
```

- [ ] **Step 6: Commit**

```bash
git add src/a2a_orchestrator/recipe_gen/ tests/recipe_gen/test_executor.py
git commit -m "feat(recipe-gen): executor and entrypoint"
```

---

## Task 8: recipe-url agent — extract + executor + main

**Files:**
- Create: `src/a2a_orchestrator/recipe_url/extract.py`
- Create: `src/a2a_orchestrator/recipe_url/executor.py`
- Create: `src/a2a_orchestrator/recipe_url/__main__.py`
- Test: `tests/recipe_url/test_extract.py`, `tests/recipe_url/test_executor.py`
- Fixture: `tests/fixtures/recipes/sample.html`

- [ ] **Step 1: Write the extract test and fixture**

`tests/fixtures/recipes/sample.html`:

```html
<!doctype html>
<html>
<head><title>Test Recipe</title></head>
<body>
<article>
<h1>Sample Chili</h1>
<p>A hearty bowl of chili.</p>
<h2>Ingredients</h2>
<ul><li>1 lb beef</li><li>1 can tomatoes</li></ul>
<h2>Steps</h2>
<ol><li>Brown beef.</li><li>Simmer one hour.</li></ol>
</article>
</body>
</html>
```

`tests/recipe_url/test_extract.py`:

```python
from pathlib import Path

from a2a_orchestrator.recipe_url.extract import extract_main_text

SAMPLE = Path(__file__).parent.parent / "fixtures" / "recipes" / "sample.html"


def test_extract_returns_readable_text():
    html = SAMPLE.read_text()
    text = extract_main_text(html)
    assert "Sample Chili" in text
    assert "Brown beef" in text


def test_extract_falls_back_to_raw_on_empty(monkeypatch):
    # Force trafilatura to return None, verify fallback still yields text
    from a2a_orchestrator.recipe_url import extract as mod

    monkeypatch.setattr(mod, "_trafilatura_extract", lambda _html: None)
    html = "<html><body><p>Just a paragraph.</p></body></html>"
    text = extract_main_text(html)
    assert "Just a paragraph" in text
```

- [ ] **Step 2: Run the test to verify it fails**

Run: `uv run pytest tests/recipe_url/test_extract.py -v`
Expected: `ImportError`.

- [ ] **Step 3: Implement extract**

`src/a2a_orchestrator/recipe_url/extract.py`:

```python
import re

import trafilatura


def _trafilatura_extract(html: str) -> str | None:
    return trafilatura.extract(html, include_comments=False, include_tables=False)


_TAG_RE = re.compile(r"<[^>]+>")
_WS_RE = re.compile(r"\s+")


def _strip_tags(html: str) -> str:
    text = _TAG_RE.sub(" ", html)
    return _WS_RE.sub(" ", text).strip()


def extract_main_text(html: str) -> str:
    text = _trafilatura_extract(html)
    if text and text.strip():
        return text.strip()
    return _strip_tags(html)
```

- [ ] **Step 4: Run the test to verify it passes**

Run: `uv run pytest tests/recipe_url/test_extract.py -v`
Expected: 2 tests PASS.

- [ ] **Step 5: Write the executor test**

`tests/recipe_url/test_executor.py`:

```python
import json
from unittest.mock import MagicMock, patch

import httpx
import respx

from a2a_orchestrator.recipe_url.executor import RecipeUrlExecutor, build_card


SAMPLE_URL = "https://example.com/chili"


class _FakeQueue:
    def __init__(self):
        self.events = []

    async def enqueue_event(self, event):
        self.events.append(event)


class _FakeContext:
    def __init__(self, text: str):
        self.task_id = "t1"
        self.context_id = "c1"
        self._t = text

    def get_user_input(self) -> str:
        return self._t


def _payload():
    return {
        "title": "Sample Chili",
        "description": "A hearty bowl of chili.",
        "ingredients": ["1 lb beef", "1 can tomatoes"],
        "prep_steps": ["chop onions"],
        "cooking_steps": ["Brown beef.", "Simmer one hour."],
        "chef_notes": None,
        "source_url": SAMPLE_URL,
    }


def test_build_card_reports_parse_skill():
    card = build_card("http://localhost:8001")
    assert card["name"] == "recipe-url"
    assert card["skills"][0]["id"] == "parse_recipe_url"


@respx.mock
async def test_executor_fetches_extracts_and_structures():
    respx.get(SAMPLE_URL).mock(
        return_value=httpx.Response(200, text="<html><body><h1>Sample Chili</h1></body></html>")
    )

    queue = _FakeQueue()
    ctx = _FakeContext(SAMPLE_URL)

    with patch(
        "a2a_orchestrator.recipe_url.executor.call_with_schema",
        return_value=_payload(),
    ), patch("a2a_orchestrator.recipe_url.executor.get_client", return_value=MagicMock()):
        await RecipeUrlExecutor().execute(ctx, queue)

    artifact_events = [e for e in queue.events if getattr(e, "kind", "") == "artifact"]
    assert artifact_events
    data = json.loads(artifact_events[0].text)
    assert data["source_url"] == SAMPLE_URL


@respx.mock
async def test_executor_fails_on_bad_http_status():
    respx.get(SAMPLE_URL).mock(return_value=httpx.Response(404))
    queue = _FakeQueue()
    ctx = _FakeContext(SAMPLE_URL)

    await RecipeUrlExecutor().execute(ctx, queue)

    statuses = [getattr(e, "state", None) for e in queue.events]
    assert "failed" in statuses


async def test_executor_fails_on_non_url_input():
    queue = _FakeQueue()
    ctx = _FakeContext("not a url")

    await RecipeUrlExecutor().execute(ctx, queue)

    statuses = [getattr(e, "state", None) for e in queue.events]
    assert "failed" in statuses
```

- [ ] **Step 6: Run the test to verify it fails**

Run: `uv run pytest tests/recipe_url/test_executor.py -v`
Expected: `ImportError`.

- [ ] **Step 7: Implement the executor**

`src/a2a_orchestrator/recipe_url/executor.py`:

```python
from dataclasses import dataclass
from typing import Any

import httpx
from pydantic import ValidationError

from a2a_orchestrator.common.claude import call_with_schema, get_client
from a2a_orchestrator.common.logging import get_logger
from a2a_orchestrator.common.persistence import save_recipe
from a2a_orchestrator.common.recipe import Recipe, recipe_json_schema
from a2a_orchestrator.recipe_url.extract import extract_main_text

log = get_logger("recipe-url")


@dataclass
class _StatusEvent:
    kind: str
    state: str
    message: str = ""


@dataclass
class _ArtifactEvent:
    kind: str
    mime_type: str
    text: str


SYSTEM_PROMPT = (
    "You are a recipe extractor. Given the main text of a recipe web page, emit a "
    "structured recipe via the emit_recipe tool. Preserve the source page's intent. "
    "Set source_url to the URL provided in the user message."
)


def build_card(url: str) -> dict[str, Any]:
    from a2a_orchestrator.common.a2a_helpers import build_agent_card

    return build_agent_card(
        name="recipe-url",
        description="Parse a recipe from a URL into a structured recipe.",
        url=url,
        skills=[
            {
                "id": "parse_recipe_url",
                "name": "parse_recipe_url",
                "description": "Fetch a URL and return a structured recipe.",
                "tags": ["recipe", "scrape"],
                "examples": ["https://example.com/ramen"],
            }
        ],
    )


def _looks_like_url(s: str) -> bool:
    return s.startswith("http://") or s.startswith("https://")


class RecipeUrlExecutor:
    async def execute(self, context, event_queue) -> None:
        user_text = context.get_user_input().strip()
        log.info("task_started", task_id=context.task_id, input=user_text[:120])

        if not _looks_like_url(user_text):
            await event_queue.enqueue_event(
                _StatusEvent("status", "failed", "input must be an http(s) URL")
            )
            return

        await event_queue.enqueue_event(_StatusEvent("status", "working", "fetching"))
        try:
            async with httpx.AsyncClient(timeout=20.0, follow_redirects=True) as client:
                resp = await client.get(user_text)
                resp.raise_for_status()
                html = resp.text
        except httpx.HTTPError as e:
            log.warning("fetch_failed", url=user_text, error=str(e))
            await event_queue.enqueue_event(
                _StatusEvent("status", "failed", f"fetch failed: {e}")
            )
            return

        await event_queue.enqueue_event(_StatusEvent("status", "working", "extracting"))
        text = extract_main_text(html)

        await event_queue.enqueue_event(_StatusEvent("status", "working", "structuring"))
        try:
            raw = call_with_schema(
                get_client(),
                system=SYSTEM_PROMPT,
                user=f"URL: {user_text}\n\n{text}",
                tool_name="emit_recipe",
                tool_description="Emit the structured recipe.",
                schema=recipe_json_schema(),
            )
            raw["source_url"] = user_text  # enforce
            recipe = Recipe(**raw)
        except (ValidationError, RuntimeError) as e:
            log.warning("structure_failed", error=str(e))
            await event_queue.enqueue_event(
                _StatusEvent("status", "failed", f"structuring failed: {e}")
            )
            return

        paths = save_recipe(recipe)
        log.info("recipe_saved", task_id=context.task_id, json=str(paths.json_path))
        await event_queue.enqueue_event(
            _ArtifactEvent("artifact", "application/json", recipe.model_dump_json())
        )
        await event_queue.enqueue_event(_StatusEvent("status", "completed"))

    async def cancel(self, context, event_queue) -> None:
        log.info("task_cancelled", task_id=getattr(context, "task_id", "?"))
```

- [ ] **Step 8: Run the tests to verify they pass**

Run: `uv run pytest tests/recipe_url -v`
Expected: 5 tests PASS.

- [ ] **Step 9: Write the `__main__` entrypoint**

`src/a2a_orchestrator/recipe_url/__main__.py`:

```python
import os

import uvicorn

from a2a_orchestrator.common.logging import configure_logging
from a2a_orchestrator.recipe_url.executor import RecipeUrlExecutor, build_card


def main() -> None:
    configure_logging(agent_name="recipe-url")
    port = int(os.environ.get("RECIPE_URL_PORT", "8001"))
    url = f"http://localhost:{port}"
    card = build_card(url)

    try:
        from a2a.server.apps import A2AStarletteApplication
        from a2a.server.request_handlers import DefaultRequestHandler
        from a2a.server.tasks import InMemoryTaskStore

        handler = DefaultRequestHandler(
            agent_executor=RecipeUrlExecutor(),
            task_store=InMemoryTaskStore(),
        )
        app = A2AStarletteApplication(agent_card=card, http_handler=handler).build()
    except ImportError:
        from a2a.server.apps import A2AFastAPIApplication  # type: ignore

        app = A2AFastAPIApplication(
            agent_card=card,
            agent_executor=RecipeUrlExecutor(),
        ).build()

    uvicorn.run(app, host="0.0.0.0", port=port)


if __name__ == "__main__":
    main()
```

- [ ] **Step 10: Commit**

```bash
git add src/a2a_orchestrator/recipe_url/ tests/recipe_url/ tests/fixtures/recipes/
git commit -m "feat(recipe-url): fetch, extract, structure recipe from URL"
```

---

## Task 9: Shell sandbox Docker image + sandbox wrapper

**Files:**
- Create: `docker/shell/Dockerfile`
- Create: `scripts/build_shell_image.sh`
- Create: `src/a2a_orchestrator/shell/sandbox.py`
- Test: `tests/shell/test_sandbox.py`

- [ ] **Step 1: Write the Dockerfile**

`docker/shell/Dockerfile`:

```dockerfile
FROM alpine:3.20

RUN apk add --no-cache \
    bash \
    coreutils \
    findutils \
    grep \
    sed \
    jq \
    ripgrep \
    busybox-extras

RUN adduser -D -u 10001 sandbox
USER sandbox
WORKDIR /work

SHELL ["/bin/sh", "-c"]
```

- [ ] **Step 2: Write the build script**

`scripts/build_shell_image.sh`:

```bash
#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")/.."
docker build -t a2a-shell:latest -f docker/shell/Dockerfile docker/shell
echo "Built a2a-shell:latest"
```

Make it executable:

```bash
chmod +x scripts/build_shell_image.sh
```

- [ ] **Step 3: Write the sandbox test**

`tests/shell/test_sandbox.py`:

```python
import asyncio
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from a2a_orchestrator.shell.sandbox import ShellResult, run_sandboxed


async def _fake_proc(stdout: bytes, stderr: bytes, returncode: int):
    proc = MagicMock()
    proc.returncode = returncode

    # stream lines
    stdout_lines = stdout.splitlines(keepends=True) or [b""]
    stderr_lines = stderr.splitlines(keepends=True) or [b""]

    async def _readline_factory(lines):
        it = iter(lines + [b""])

        async def _readline():
            return next(it)

        return _readline

    proc.stdout = MagicMock()
    proc.stdout.readline = await _readline_factory(stdout_lines)
    proc.stderr = MagicMock()
    proc.stderr.readline = await _readline_factory(stderr_lines)
    proc.wait = AsyncMock(return_value=returncode)
    proc.kill = MagicMock()
    return proc


async def test_run_sandboxed_collects_stdout_and_exit_code(monkeypatch):
    async def _create(*args, **kwargs):
        return await _fake_proc(b"hello\n", b"", 0)

    lines: list[tuple[str, str]] = []

    async def _on_line(stream: str, line: str):
        lines.append((stream, line))

    with patch(
        "asyncio.create_subprocess_exec",
        side_effect=_create,
    ):
        result = await run_sandboxed("echo hello", on_line=_on_line, timeout=5)

    assert isinstance(result, ShellResult)
    assert result.exit_code == 0
    assert "hello" in result.stdout
    assert ("stdout", "hello\n") in lines


async def test_run_sandboxed_times_out():
    async def _hang(*args, **kwargs):
        # Proc that never finishes
        proc = MagicMock()
        proc.returncode = None
        proc.stdout = MagicMock()
        proc.stdout.readline = AsyncMock(return_value=b"")
        proc.stderr = MagicMock()
        proc.stderr.readline = AsyncMock(return_value=b"")

        async def _wait():
            await asyncio.sleep(10)
            return 0

        proc.wait = AsyncMock(side_effect=_wait)
        proc.kill = MagicMock()
        return proc

    with patch("asyncio.create_subprocess_exec", side_effect=_hang):
        result = await run_sandboxed("sleep 9", on_line=None, timeout=0.2)

    assert result.exit_code == -1
    assert result.timed_out is True


async def test_run_sandboxed_truncates_large_output():
    big = b"x" * (2 * 1024 * 1024) + b"\n"

    async def _create(*args, **kwargs):
        return await _fake_proc(big, b"", 0)

    with patch("asyncio.create_subprocess_exec", side_effect=_create):
        result = await run_sandboxed("cat big", on_line=None, timeout=5)

    assert len(result.stdout) <= 1024 * 1024
    assert result.truncated_stdout is True
```

- [ ] **Step 4: Run the test to verify it fails**

Run: `uv run pytest tests/shell/test_sandbox.py -v`
Expected: `ImportError`.

- [ ] **Step 5: Implement the sandbox**

`src/a2a_orchestrator/shell/sandbox.py`:

```python
import asyncio
import os
from dataclasses import dataclass
from typing import Awaitable, Callable

_MAX_STREAM_BYTES = 1024 * 1024  # 1 MB per stream


@dataclass
class ShellResult:
    stdout: str
    stderr: str
    exit_code: int
    timed_out: bool = False
    truncated_stdout: bool = False
    truncated_stderr: bool = False


def _docker_cmd(command: str) -> list[str]:
    workspace = os.path.abspath(os.environ.get("WORKSPACE_DIR", "./workspace"))
    return [
        "docker", "run", "--rm",
        "--network=none",
        "--read-only",
        "--tmpfs", "/tmp:size=64m",
        "--memory=256m",
        "--cpus=0.5",
        "--pids-limit=64",
        "-v", f"{workspace}:/work:ro",
        "-w", "/work",
        "a2a-shell:latest",
        "sh", "-c", command,
    ]


async def _read_stream(
    stream,
    label: str,
    on_line: Callable[[str, str], Awaitable[None]] | None,
    buf: bytearray,
    limit: int,
) -> bool:
    """Read lines until EOF. Returns True if truncated."""
    truncated = False
    while True:
        line = await stream.readline()
        if not line:
            break
        if len(buf) < limit:
            room = limit - len(buf)
            buf.extend(line[:room])
            if len(line) > room:
                truncated = True
        else:
            truncated = True
        if on_line:
            try:
                await on_line(label, line.decode("utf-8", errors="replace"))
            except Exception:  # noqa: BLE001
                pass
    return truncated


async def run_sandboxed(
    command: str,
    *,
    on_line: Callable[[str, str], Awaitable[None]] | None = None,
    timeout: float = 30.0,
) -> ShellResult:
    proc = await asyncio.create_subprocess_exec(
        *_docker_cmd(command),
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE,
    )

    stdout_buf = bytearray()
    stderr_buf = bytearray()

    async def _run():
        out_trunc, err_trunc = await asyncio.gather(
            _read_stream(proc.stdout, "stdout", on_line, stdout_buf, _MAX_STREAM_BYTES),
            _read_stream(proc.stderr, "stderr", on_line, stderr_buf, _MAX_STREAM_BYTES),
        )
        rc = await proc.wait()
        return rc, out_trunc, err_trunc

    try:
        rc, out_trunc, err_trunc = await asyncio.wait_for(_run(), timeout=timeout)
    except asyncio.TimeoutError:
        proc.kill()
        try:
            await proc.wait()
        except Exception:  # noqa: BLE001
            pass
        return ShellResult(
            stdout=stdout_buf.decode("utf-8", errors="replace"),
            stderr=stderr_buf.decode("utf-8", errors="replace"),
            exit_code=-1,
            timed_out=True,
        )

    return ShellResult(
        stdout=stdout_buf.decode("utf-8", errors="replace"),
        stderr=stderr_buf.decode("utf-8", errors="replace"),
        exit_code=rc,
        truncated_stdout=out_trunc,
        truncated_stderr=err_trunc,
    )


def docker_available() -> bool:
    import subprocess
    try:
        subprocess.run(
            ["docker", "info"],
            check=True,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            timeout=5,
        )
        return True
    except Exception:  # noqa: BLE001
        return False
```

- [ ] **Step 6: Run the test to verify it passes**

Run: `uv run pytest tests/shell/test_sandbox.py -v`
Expected: 3 tests PASS.

- [ ] **Step 7: Commit**

```bash
git add docker/ scripts/build_shell_image.sh src/a2a_orchestrator/shell/sandbox.py tests/shell/test_sandbox.py
git commit -m "feat(shell): dockerized sandbox wrapper"
```

---

## Task 10: Shell agent — executor + main

**Files:**
- Create: `src/a2a_orchestrator/shell/executor.py`
- Create: `src/a2a_orchestrator/shell/__main__.py`
- Test: `tests/shell/test_executor.py`

- [ ] **Step 1: Write the failing test**

`tests/shell/test_executor.py`:

```python
import json
from unittest.mock import AsyncMock, patch

from a2a_orchestrator.shell.executor import ShellExecutor, build_card
from a2a_orchestrator.shell.sandbox import ShellResult


class _FakeQueue:
    def __init__(self):
        self.events = []

    async def enqueue_event(self, e):
        self.events.append(e)


class _Ctx:
    def __init__(self, text: str):
        self.task_id = "t"
        self.context_id = "c"
        self._t = text

    def get_user_input(self) -> str:
        return self._t


def test_build_card_reports_run_shell_skill():
    card = build_card("http://localhost:8003")
    assert card["name"] == "shell"
    assert card["skills"][0]["id"] == "run_shell"


async def test_executor_runs_command_and_returns_artifact():
    q = _FakeQueue()
    ctx = _Ctx("ls /work")
    fake = ShellResult(stdout="a\nb\n", stderr="", exit_code=0)

    with patch(
        "a2a_orchestrator.shell.executor.run_sandboxed",
        new=AsyncMock(return_value=fake),
    ):
        await ShellExecutor().execute(ctx, q)

    artifacts = [e for e in q.events if getattr(e, "kind", "") == "artifact"]
    assert artifacts
    data = json.loads(artifacts[0].text)
    assert data["stdout"] == "a\nb\n"
    assert data["exit_code"] == 0
    assert data["truncated_stdout"] is False


async def test_executor_streams_stdout_lines_as_text_parts():
    q = _FakeQueue()
    ctx = _Ctx("ls /work")

    async def _fake_run(command, *, on_line, timeout):
        await on_line("stdout", "line1\n")
        await on_line("stderr", "warn\n")
        return ShellResult(stdout="line1\n", stderr="warn\n", exit_code=0)

    with patch("a2a_orchestrator.shell.executor.run_sandboxed", side_effect=_fake_run):
        await ShellExecutor().execute(ctx, q)

    text_events = [e for e in q.events if getattr(e, "kind", "") == "text"]
    texts = [e.text for e in text_events]
    assert any("line1" in t for t in texts)
    assert any("[stderr] warn" in t or "warn" in t for t in texts)


async def test_executor_reports_timeout():
    q = _FakeQueue()
    ctx = _Ctx("sleep 99")
    fake = ShellResult(stdout="", stderr="", exit_code=-1, timed_out=True)

    with patch(
        "a2a_orchestrator.shell.executor.run_sandboxed",
        new=AsyncMock(return_value=fake),
    ):
        await ShellExecutor().execute(ctx, q)

    artifacts = [e for e in q.events if getattr(e, "kind", "") == "artifact"]
    assert artifacts
    data = json.loads(artifacts[0].text)
    assert data["timed_out"] is True
    assert data["exit_code"] == -1
```

- [ ] **Step 2: Run the test to verify it fails**

Run: `uv run pytest tests/shell/test_executor.py -v`
Expected: `ImportError`.

- [ ] **Step 3: Implement the executor**

`src/a2a_orchestrator/shell/executor.py`:

```python
import json
from dataclasses import dataclass
from typing import Any

from a2a_orchestrator.common.logging import get_logger
from a2a_orchestrator.shell.sandbox import run_sandboxed

log = get_logger("shell")


@dataclass
class _StatusEvent:
    kind: str
    state: str
    message: str = ""


@dataclass
class _TextEvent:
    kind: str  # "text"
    text: str


@dataclass
class _ArtifactEvent:
    kind: str  # "artifact"
    mime_type: str
    text: str


def build_card(url: str) -> dict[str, Any]:
    from a2a_orchestrator.common.a2a_helpers import build_agent_card

    return build_agent_card(
        name="shell",
        description="Run a sandboxed shell command in a read-only workspace.",
        url=url,
        skills=[
            {
                "id": "run_shell",
                "name": "run_shell",
                "description": "Run a shell command in a sandboxed container. "
                               "Read-only workspace at /work. 30s timeout.",
                "tags": ["shell", "sandbox"],
                "examples": ["ls /work", "grep -r 'ramen' /work/recipes"],
            }
        ],
    )


class ShellExecutor:
    async def execute(self, context, event_queue) -> None:
        command = context.get_user_input().strip()
        log.info("task_started", task_id=context.task_id, command=command[:200])

        if not command:
            await event_queue.enqueue_event(_StatusEvent("status", "failed", "empty command"))
            return

        await event_queue.enqueue_event(_StatusEvent("status", "working", f"running: {command}"))

        async def _on_line(stream: str, line: str) -> None:
            prefix = "" if stream == "stdout" else "[stderr] "
            await event_queue.enqueue_event(_TextEvent("text", f"{prefix}{line.rstrip()}"))

        result = await run_sandboxed(command, on_line=_on_line, timeout=30.0)

        payload = {
            "stdout": result.stdout,
            "stderr": result.stderr,
            "exit_code": result.exit_code,
            "timed_out": result.timed_out,
            "truncated_stdout": result.truncated_stdout,
            "truncated_stderr": result.truncated_stderr,
        }
        await event_queue.enqueue_event(
            _ArtifactEvent("artifact", "application/json", json.dumps(payload))
        )
        await event_queue.enqueue_event(_StatusEvent("status", "completed"))
        log.info("task_completed", task_id=context.task_id, exit_code=result.exit_code)

    async def cancel(self, context, event_queue) -> None:
        log.info("task_cancelled", task_id=getattr(context, "task_id", "?"))
```

- [ ] **Step 4: Run the test to verify it passes**

Run: `uv run pytest tests/shell/test_executor.py -v`
Expected: 4 tests PASS.

- [ ] **Step 5: Write the `__main__` entrypoint**

`src/a2a_orchestrator/shell/__main__.py`:

```python
import os
import sys

import uvicorn

from a2a_orchestrator.common.logging import configure_logging, get_logger
from a2a_orchestrator.shell.executor import ShellExecutor, build_card
from a2a_orchestrator.shell.sandbox import docker_available


def main() -> None:
    configure_logging(agent_name="shell")
    log = get_logger("shell")
    if not docker_available():
        log.error("docker_not_available", hint="start Docker or run `make shell-image`")
        sys.exit(1)

    port = int(os.environ.get("SHELL_PORT", "8003"))
    url = f"http://localhost:{port}"
    card = build_card(url)

    try:
        from a2a.server.apps import A2AStarletteApplication
        from a2a.server.request_handlers import DefaultRequestHandler
        from a2a.server.tasks import InMemoryTaskStore

        handler = DefaultRequestHandler(
            agent_executor=ShellExecutor(),
            task_store=InMemoryTaskStore(),
        )
        app = A2AStarletteApplication(agent_card=card, http_handler=handler).build()
    except ImportError:
        from a2a.server.apps import A2AFastAPIApplication  # type: ignore

        app = A2AFastAPIApplication(
            agent_card=card,
            agent_executor=ShellExecutor(),
        ).build()

    uvicorn.run(app, host="0.0.0.0", port=port)


if __name__ == "__main__":
    main()
```

- [ ] **Step 6: Commit**

```bash
git add src/a2a_orchestrator/shell/ tests/shell/test_executor.py
git commit -m "feat(shell): executor, entrypoint, streams stdout/stderr"
```

---

## Task 11: Orchestrator planner module

**Files:**
- Create: `src/a2a_orchestrator/orchestrator/planner.py`
- Test: `tests/orchestrator/test_planner.py`

- [ ] **Step 1: Write the failing test**

`tests/orchestrator/test_planner.py`:

```python
from unittest.mock import MagicMock, patch

from a2a_orchestrator.orchestrator.planner import (
    PlanStep,
    build_plan,
    format_capabilities,
    substitute_placeholders,
    synthesize,
)


def _card(name: str, skill_id: str) -> dict:
    return {
        "name": name,
        "description": f"{name} desc",
        "skills": [
            {"id": skill_id, "name": skill_id, "description": f"{skill_id} skill",
             "examples": ["example input"]}
        ],
    }


def test_format_capabilities_lists_each_skill():
    cards = [_card("recipe-url", "parse_recipe_url"), _card("shell", "run_shell")]
    text = format_capabilities(cards)
    assert "recipe-url" in text
    assert "parse_recipe_url" in text
    assert "shell" in text
    assert "run_shell" in text


def test_build_plan_returns_steps():
    cards = [_card("recipe-url", "parse_recipe_url")]
    fake = {
        "steps": [
            {"agent": "recipe-url", "skill": "parse_recipe_url",
             "input": "https://example.com/ramen"}
        ]
    }
    with patch(
        "a2a_orchestrator.orchestrator.planner.call_with_schema",
        return_value=fake,
    ), patch("a2a_orchestrator.orchestrator.planner.get_client", return_value=MagicMock()):
        steps = build_plan("fetch this: https://example.com/ramen", cards)
    assert len(steps) == 1
    assert steps[0] == PlanStep(
        agent="recipe-url", skill="parse_recipe_url", input="https://example.com/ramen"
    )


def test_build_plan_empty_is_fine():
    cards = [_card("recipe-url", "parse_recipe_url")]
    with patch(
        "a2a_orchestrator.orchestrator.planner.call_with_schema",
        return_value={"steps": []},
    ), patch("a2a_orchestrator.orchestrator.planner.get_client", return_value=MagicMock()):
        steps = build_plan("just say hi", cards)
    assert steps == []


def test_substitute_placeholders_replaces_prior_step_refs():
    outputs = {1: "hello world"}
    assert substitute_placeholders("say {{step_1.output}}", outputs) == "say hello world"
    assert substitute_placeholders("no refs here", outputs) == "no refs here"


def test_substitute_placeholders_missing_ref_left_as_is():
    outputs: dict[int, str] = {}
    assert substitute_placeholders("x {{step_9.output}}", outputs) == "x {{step_9.output}}"


async def test_synthesize_streams_text():
    async def _gen():
        for c in ["Result: ", "ok"]:
            yield c

    class _FakeAsyncClient:
        pass

    with patch(
        "a2a_orchestrator.orchestrator.planner.stream_text",
        return_value=_gen(),
    ), patch(
        "a2a_orchestrator.orchestrator.planner.get_async_client",
        return_value=_FakeAsyncClient(),
    ):
        chunks = []
        async for c in synthesize("q", step_outputs={1: "ok"}):
            chunks.append(c)
        assert "".join(chunks) == "Result: ok"
```

- [ ] **Step 2: Run the test to verify it fails**

Run: `uv run pytest tests/orchestrator/test_planner.py -v`
Expected: `ImportError`.

- [ ] **Step 3: Implement the planner**

`src/a2a_orchestrator/orchestrator/planner.py`:

```python
import re
from dataclasses import dataclass
from typing import AsyncIterator

from a2a_orchestrator.common.claude import (
    call_with_schema,
    get_async_client,
    get_client,
    stream_text,
)

PLAN_SCHEMA = {
    "type": "object",
    "properties": {
        "steps": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "agent": {"type": "string"},
                    "skill": {"type": "string"},
                    "input": {"type": "string"},
                },
                "required": ["agent", "skill", "input"],
            },
        }
    },
    "required": ["steps"],
}

PLAN_SYSTEM = (
    "You are a planner. Given a user request and a list of available agents and their "
    "skills, return a sequential plan as a list of steps. Each step names an agent and "
    "skill from the capability list and provides a concrete input string for that "
    "skill. Use no agent not listed. Reference prior step output with "
    "{{step_N.output}} placeholders (N is 1-based). Empty steps list is fine if no "
    "agent is needed. Emit the plan via the emit_plan tool."
)

SYNTH_SYSTEM = (
    "You are a synthesizer. Given the user's original request and the outputs of each "
    "step, write a concise natural-language answer. If step outputs contain JSON, you "
    "may quote key fields. Do not repeat raw JSON wholesale."
)


@dataclass(frozen=True)
class PlanStep:
    agent: str
    skill: str
    input: str


def format_capabilities(cards: list[dict]) -> str:
    lines: list[str] = []
    for c in cards:
        lines.append(f"- {c['name']}: {c.get('description', '')}")
        for s in c.get("skills", []):
            ex = s.get("examples") or []
            ex_line = f" (e.g., {ex[0]})" if ex else ""
            lines.append(f"    • skill `{s['id']}` — {s.get('description', '')}{ex_line}")
    return "\n".join(lines) if lines else "(no agents available)"


def build_plan(user_request: str, cards: list[dict]) -> list[PlanStep]:
    caps = format_capabilities(cards)
    user_msg = f"User request:\n{user_request}\n\nAvailable agents:\n{caps}"
    raw = call_with_schema(
        get_client(),
        system=PLAN_SYSTEM,
        user=user_msg,
        tool_name="emit_plan",
        tool_description="Emit the sequential plan.",
        schema=PLAN_SCHEMA,
    )
    return [PlanStep(**s) for s in raw.get("steps", [])]


_PLACEHOLDER_RE = re.compile(r"\{\{step_(\d+)\.output\}\}")


def substitute_placeholders(text: str, outputs: dict[int, str]) -> str:
    def _repl(m: re.Match[str]) -> str:
        n = int(m.group(1))
        return outputs.get(n, m.group(0))

    return _PLACEHOLDER_RE.sub(_repl, text)


async def synthesize(
    user_request: str, *, step_outputs: dict[int, str]
) -> AsyncIterator[str]:
    outputs_text = "\n\n".join(
        f"Step {n} output:\n{out}" for n, out in sorted(step_outputs.items())
    )
    user_msg = (
        f"Original request:\n{user_request}\n\n"
        f"{outputs_text if outputs_text else '(no steps were needed)'}"
    )
    async for chunk in stream_text(get_async_client(), system=SYNTH_SYSTEM, user=user_msg):
        yield chunk
```

- [ ] **Step 4: Run the test to verify it passes**

Run: `uv run pytest tests/orchestrator/test_planner.py -v`
Expected: 6 tests PASS.

- [ ] **Step 5: Commit**

```bash
git add src/a2a_orchestrator/orchestrator/planner.py tests/orchestrator/test_planner.py
git commit -m "feat(orchestrator): planner with plan, substitute, synthesize"
```

---

## Task 12: Orchestrator executor (plan → dispatch → synthesize)

**Files:**
- Create: `src/a2a_orchestrator/orchestrator/executor.py`
- Test: `tests/orchestrator/test_executor.py`

- [ ] **Step 1: Write the failing test**

`tests/orchestrator/test_executor.py`:

```python
from unittest.mock import AsyncMock, patch

from a2a_orchestrator.orchestrator.executor import OrchestratorExecutor, build_card
from a2a_orchestrator.orchestrator.planner import PlanStep


class _FakeQueue:
    def __init__(self):
        self.events = []

    async def enqueue_event(self, e):
        self.events.append(e)


class _Ctx:
    def __init__(self, text: str):
        self.task_id = "t"
        self.context_id = "c"
        self._t = text

    def get_user_input(self) -> str:
        return self._t


def _card(name: str, port: int, skill: str) -> dict:
    return {
        "name": name,
        "description": f"{name} desc",
        "url": f"http://localhost:{port}",
        "skills": [{"id": skill, "name": skill, "description": "", "examples": []}],
    }


def test_build_card_reports_orchestrate_skill():
    card = build_card("http://localhost:8000")
    assert card["name"] == "orchestrator"
    assert card["skills"][0]["id"] == "orchestrate"


async def test_executor_plans_dispatches_synthesizes(monkeypatch):
    cards = [_card("recipe-url", 8001, "parse_recipe_url")]
    plan = [PlanStep(agent="recipe-url", skill="parse_recipe_url", input="https://x/y")]

    async def _fake_dispatch(agent_url, skill, text, on_event):
        await on_event(("text", "[recipe-url] working: fetching"))
        return '{"title":"X"}'

    async def _fake_synth(*args, **kwargs):
        for c in ["done: ", "X"]:
            yield c

    q = _FakeQueue()

    with patch(
        "a2a_orchestrator.orchestrator.executor.discover_agents",
        new=AsyncMock(return_value=cards),
    ), patch(
        "a2a_orchestrator.orchestrator.executor.build_plan", return_value=plan,
    ), patch(
        "a2a_orchestrator.orchestrator.executor.dispatch_step", side_effect=_fake_dispatch,
    ), patch(
        "a2a_orchestrator.orchestrator.executor.synthesize", side_effect=_fake_synth,
    ):
        await OrchestratorExecutor().execute(_Ctx("scrape https://x/y"), q)

    texts = [e.text for e in q.events if getattr(e, "kind", "") == "text"]
    assert any("Plan:" in t for t in texts)
    assert any("[recipe-url]" in t for t in texts)
    assert any("done: " in t or "X" in t for t in texts)
    statuses = [getattr(e, "state", None) for e in q.events]
    assert statuses[-1] == "completed"


async def test_executor_substitutes_placeholders():
    cards = [
        _card("recipe-url", 8001, "parse_recipe_url"),
        _card("shell", 8003, "run_shell"),
    ]
    plan = [
        PlanStep(agent="recipe-url", skill="parse_recipe_url", input="https://x/y"),
        PlanStep(agent="shell", skill="run_shell", input="echo {{step_1.output}}"),
    ]
    calls: list[tuple[str, str]] = []

    async def _fake_dispatch(agent_url, skill, text, on_event):
        calls.append((skill, text))
        return '{"title":"X"}' if skill == "parse_recipe_url" else "ok"

    async def _fake_synth(*a, **k):
        if False:
            yield  # make it an async gen
        return

    q = _FakeQueue()

    with patch(
        "a2a_orchestrator.orchestrator.executor.discover_agents",
        new=AsyncMock(return_value=cards),
    ), patch(
        "a2a_orchestrator.orchestrator.executor.build_plan", return_value=plan,
    ), patch(
        "a2a_orchestrator.orchestrator.executor.dispatch_step", side_effect=_fake_dispatch,
    ), patch(
        "a2a_orchestrator.orchestrator.executor.synthesize", side_effect=_fake_synth,
    ):
        await OrchestratorExecutor().execute(_Ctx("go"), q)

    assert calls[0] == ("parse_recipe_url", "https://x/y")
    assert calls[1] == ("run_shell", 'echo {"title":"X"}')


async def test_executor_aborts_on_step_failure():
    cards = [_card("shell", 8003, "run_shell")]
    plan = [PlanStep(agent="shell", skill="run_shell", input="boom")]

    async def _fake_dispatch(*args, **kwargs):
        raise RuntimeError("child failed")

    q = _FakeQueue()

    with patch(
        "a2a_orchestrator.orchestrator.executor.discover_agents",
        new=AsyncMock(return_value=cards),
    ), patch(
        "a2a_orchestrator.orchestrator.executor.build_plan", return_value=plan,
    ), patch(
        "a2a_orchestrator.orchestrator.executor.dispatch_step", side_effect=_fake_dispatch,
    ):
        await OrchestratorExecutor().execute(_Ctx("go"), q)

    statuses = [getattr(e, "state", None) for e in q.events]
    assert "failed" in statuses
```

- [ ] **Step 2: Run the test to verify it fails**

Run: `uv run pytest tests/orchestrator/test_executor.py -v`
Expected: `ImportError`.

- [ ] **Step 3: Implement the dispatcher and executor**

`src/a2a_orchestrator/orchestrator/executor.py`:

```python
import json
import os
from dataclasses import dataclass
from typing import Any, Awaitable, Callable

from a2a_orchestrator.common.a2a_helpers import build_agent_card, discover_agents
from a2a_orchestrator.common.logging import get_logger
from a2a_orchestrator.orchestrator.planner import (
    PlanStep,
    build_plan,
    substitute_placeholders,
    synthesize,
)

log = get_logger("orchestrator")


@dataclass
class _StatusEvent:
    kind: str
    state: str
    message: str = ""


@dataclass
class _TextEvent:
    kind: str  # "text"
    text: str


def build_card(url: str) -> dict[str, Any]:
    return build_agent_card(
        name="orchestrator",
        description="Plan, dispatch, and synthesize across specialist agents.",
        url=url,
        skills=[
            {
                "id": "orchestrate",
                "name": "orchestrate",
                "description": "Accept a freeform request, plan with specialist agents, return a synthesized answer.",
                "tags": ["orchestrate"],
                "examples": [
                    "Parse https://example.com/ramen and find any similar recipes I already have.",
                    "Give me a vegan ramen recipe.",
                ],
            }
        ],
    )


async def dispatch_step(
    agent_url: str,
    skill: str,
    input_text: str,
    on_event: Callable[[tuple[str, str]], Awaitable[None]],
) -> str:
    """Call a child agent via A2A, stream its events upward, return the final artifact text.

    on_event receives (label, text) tuples, where label is "text" or "status".
    """
    try:
        from a2a.client import A2AClient
        from a2a.types import Message, TextPart
    except ImportError:  # pragma: no cover
        raise RuntimeError("a2a-sdk client imports failed; update to a recent SDK")

    # SDK APIs vary: construct a Message with one text part and call the streaming send.
    import httpx

    async with httpx.AsyncClient(timeout=None) as http:
        client = A2AClient(httpx_client=http, url=agent_url)
        message = Message(
            role="user",
            parts=[TextPart(text=input_text)],
            messageId=os.urandom(8).hex(),
        )
        final_artifact_text = ""
        async for event in client.send_message_streaming(message=message):
            kind = getattr(event, "kind", "") or type(event).__name__.lower()
            if "status" in kind.lower():
                state = getattr(getattr(event, "status", None), "state", "working")
                msg = getattr(getattr(event, "status", None), "message", "")
                await on_event(("text", f"[{skill}] {state}: {msg}"))
                if state == "failed":
                    raise RuntimeError(f"{skill} failed: {msg}")
            elif "artifact" in kind.lower():
                artifact = getattr(event, "artifact", event)
                parts = getattr(artifact, "parts", [])
                for p in parts:
                    t = getattr(p, "text", None)
                    if t:
                        final_artifact_text = t
                        await on_event(("text", f"[{skill}] artifact received"))
            else:
                text = getattr(event, "text", None)
                if text:
                    await on_event(("text", f"[{skill}] {text}"))
        if not final_artifact_text:
            raise RuntimeError(f"{skill} returned no artifact")
        return final_artifact_text


class OrchestratorExecutor:
    async def execute(self, context, event_queue) -> None:
        user_text = context.get_user_input()
        log.info("task_started", task_id=context.task_id, prompt=user_text[:160])

        await event_queue.enqueue_event(_StatusEvent("status", "working", "discovering"))
        ports = [int(p) for p in os.environ.get(
            "A2A_DISCOVERY_PORTS", "8001,8002,8003"
        ).split(",") if p.strip()]
        cards = await discover_agents(ports)
        log.info("discovery", task_id=context.task_id, agents=[c["name"] for c in cards])

        await event_queue.enqueue_event(_StatusEvent("status", "working", "planning"))
        try:
            plan: list[PlanStep] = build_plan(user_text, cards)
        except Exception as e:  # noqa: BLE001
            log.exception("plan_failed")
            await event_queue.enqueue_event(_StatusEvent("status", "failed", f"plan: {e}"))
            return

        plan_summary = (
            "Plan: " + "; ".join(f"{i+1}) {s.agent}:{s.skill}" for i, s in enumerate(plan))
            if plan else "Plan: (none — synthesizing directly)"
        )
        await event_queue.enqueue_event(_TextEvent("text", plan_summary))

        step_outputs: dict[int, str] = {}
        for idx, step in enumerate(plan, start=1):
            agent_card = next((c for c in cards if c["name"] == step.agent), None)
            if not agent_card:
                await event_queue.enqueue_event(
                    _StatusEvent("status", "failed", f"unknown agent {step.agent}")
                )
                return
            resolved_input = substitute_placeholders(step.input, step_outputs)

            async def _on_event(pair: tuple[str, str]) -> None:
                label, text = pair
                await event_queue.enqueue_event(_TextEvent("text", text))

            try:
                output = await dispatch_step(
                    agent_card["url"], step.skill, resolved_input, _on_event
                )
            except Exception as e:  # noqa: BLE001
                log.exception("step_failed", step=idx)
                await event_queue.enqueue_event(
                    _StatusEvent("status", "failed", f"step {idx}: {e}")
                )
                return
            step_outputs[idx] = output

        await event_queue.enqueue_event(_StatusEvent("status", "working", "synthesizing"))
        try:
            async for chunk in synthesize(user_text, step_outputs=step_outputs):
                await event_queue.enqueue_event(_TextEvent("text", chunk))
        except Exception as e:  # noqa: BLE001
            log.exception("synthesis_failed")
            await event_queue.enqueue_event(
                _StatusEvent("status", "failed", f"synthesis: {e}")
            )
            return

        await event_queue.enqueue_event(_StatusEvent("status", "completed"))
        log.info("task_completed", task_id=context.task_id)

    async def cancel(self, context, event_queue) -> None:
        log.info("task_cancelled")
```

- [ ] **Step 4: Run the test to verify it passes**

Run: `uv run pytest tests/orchestrator/test_executor.py -v`
Expected: 4 tests PASS.

- [ ] **Step 5: Commit**

```bash
git add src/a2a_orchestrator/orchestrator/executor.py tests/orchestrator/test_executor.py
git commit -m "feat(orchestrator): executor runs plan → dispatch → synthesize"
```

---

## Task 13: Orchestrator `__main__` entrypoint

**Files:**
- Create: `src/a2a_orchestrator/orchestrator/__main__.py`

- [ ] **Step 1: Write the entrypoint**

`src/a2a_orchestrator/orchestrator/__main__.py`:

```python
import os

import uvicorn

from a2a_orchestrator.common.logging import configure_logging
from a2a_orchestrator.orchestrator.executor import OrchestratorExecutor, build_card


def main() -> None:
    configure_logging(agent_name="orchestrator")
    port = int(os.environ.get("ORCHESTRATOR_PORT", "8000"))
    url = f"http://localhost:{port}"
    card = build_card(url)

    try:
        from a2a.server.apps import A2AStarletteApplication
        from a2a.server.request_handlers import DefaultRequestHandler
        from a2a.server.tasks import InMemoryTaskStore

        handler = DefaultRequestHandler(
            agent_executor=OrchestratorExecutor(),
            task_store=InMemoryTaskStore(),
        )
        app = A2AStarletteApplication(agent_card=card, http_handler=handler).build()
    except ImportError:
        from a2a.server.apps import A2AFastAPIApplication  # type: ignore

        app = A2AFastAPIApplication(
            agent_card=card,
            agent_executor=OrchestratorExecutor(),
        ).build()

    uvicorn.run(app, host="0.0.0.0", port=port)


if __name__ == "__main__":
    main()
```

- [ ] **Step 2: Run full test suite**

Run: `uv run pytest -v`
Expected: all tests PASS (expect ~30+ tests across tasks 2–12).

- [ ] **Step 3: Commit**

```bash
git add src/a2a_orchestrator/orchestrator/__main__.py
git commit -m "feat(orchestrator): entrypoint"
```

---

## Task 14: Run-all script and README

**Files:**
- Create: `scripts/run_all.sh`
- Create: `README.md`

- [ ] **Step 1: Write the run-all script**

`scripts/run_all.sh`:

```bash
#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")/.."

# Load .env if present
if [ -f .env ]; then
  set -a
  # shellcheck disable=SC1091
  . ./.env
  set +a
fi

pids=()
cleanup() {
  echo "Stopping agents..."
  for pid in "${pids[@]}"; do
    kill "$pid" 2>/dev/null || true
  done
  wait
}
trap cleanup INT TERM EXIT

echo "Starting recipe-url on :${RECIPE_URL_PORT:-8001}"
uv run python -m a2a_orchestrator.recipe_url &
pids+=($!)

echo "Starting recipe-gen on :${RECIPE_GEN_PORT:-8002}"
uv run python -m a2a_orchestrator.recipe_gen &
pids+=($!)

echo "Starting shell on :${SHELL_PORT:-8003} (requires Docker)"
uv run python -m a2a_orchestrator.shell &
pids+=($!)

# Give specialists ~1s to open ports before orchestrator runs discovery
sleep 1

echo "Starting orchestrator on :${ORCHESTRATOR_PORT:-8000}"
uv run python -m a2a_orchestrator.orchestrator &
pids+=($!)

echo
echo "All agents launched. Ctrl-C to stop."
wait
```

Make it executable:

```bash
chmod +x scripts/run_all.sh
```

- [ ] **Step 2: Write the README**

`README.md`:

````markdown
# A2A Orchestrator

Four A2A-compliant agents on localhost:

| Agent        | Port | Skill               |
|--------------|------|---------------------|
| orchestrator | 8000 | `orchestrate`       |
| recipe-url   | 8001 | `parse_recipe_url`  |
| recipe-gen   | 8002 | `generate_recipe`   |
| shell        | 8003 | `run_shell` (Docker sandbox) |

The orchestrator auto-discovers the other three at startup, plans with Claude
Haiku 4.5, dispatches sequentially, and returns a synthesized answer.

## Setup

1. Install [uv](https://docs.astral.sh/uv/).
2. `uv sync`
3. `cp .env.example .env` and fill in `ANTHROPIC_API_KEY`.
4. `make shell-image` (requires Docker running).

## Run

```bash
make run-all
```

All four agents start in the foreground. Ctrl-C stops them.

## Try it

```bash
curl -s http://localhost:8000/.well-known/agent-card.json | jq .
```

Send a streaming request (example, adjust to current A2A client shape):

```bash
curl -N -X POST http://localhost:8000/ \
  -H 'content-type: application/json' \
  -d '{
    "jsonrpc": "2.0",
    "id": "1",
    "method": "message/stream",
    "params": {
      "message": {
        "role": "user",
        "parts": [{"kind": "text", "text": "Give me a vegan ramen recipe."}],
        "messageId": "m1"
      }
    }
  }'
```

Generated recipes land in `./recipes/` as `.json` and `.md`.

## Test

```bash
make test
```

## Layout

- `src/a2a_orchestrator/common/` — shared model, Claude helper, persistence, A2A helpers
- `src/a2a_orchestrator/orchestrator/` — planner + dispatch loop
- `src/a2a_orchestrator/recipe_url/` — fetch + extract + structure
- `src/a2a_orchestrator/recipe_gen/` — structured generation
- `src/a2a_orchestrator/shell/` — Dockerized sandboxed shell
````

- [ ] **Step 3: Commit**

```bash
git add scripts/run_all.sh README.md
git commit -m "feat: run-all script and README"
```

---

## Task 15: Final verification

- [ ] **Step 1: Full test suite passes**

Run: `uv run pytest -v`
Expected: all tests green.

- [ ] **Step 2: Ruff clean**

Run: `uv run ruff check . && uv run ruff format --check .`
Expected: no issues.

- [ ] **Step 3: Build shell image**

Run: `make shell-image`
Expected: `Built a2a-shell:latest`.

- [ ] **Step 4: Smoke-test startup**

Run in a terminal: `make run-all`

In another terminal:

```bash
curl -s http://localhost:8000/.well-known/agent-card.json | jq .name
curl -s http://localhost:8001/.well-known/agent-card.json | jq .name
curl -s http://localhost:8002/.well-known/agent-card.json | jq .name
curl -s http://localhost:8003/.well-known/agent-card.json | jq .name
```

Expected: `"orchestrator"`, `"recipe-url"`, `"recipe-gen"`, `"shell"`.

Send a request to the orchestrator (see README for curl example). Watch streaming response; confirm a file lands in `./recipes/` if the plan used a recipe agent.

Stop with Ctrl-C.

- [ ] **Step 5: Final commit if anything changed**

```bash
git status
# if anything, git add -A && git commit -m "fix: final polish"
```

---

## Notes for the implementer

- **A2A SDK drift:** If `a2a.server.apps.A2AStarletteApplication` / `DefaultRequestHandler` / `InMemoryTaskStore` are not in your installed version, check `pip show a2a-sdk` for location and adjust imports. The executor contract (`execute(context, event_queue)`, `cancel(...)`) is the stable part. The client streaming API may also be `send_message_streaming` vs an older `send_message_stream`; consult the SDK.
- **Event shapes:** The `_StatusEvent` / `_TextEvent` / `_ArtifactEvent` dataclasses are internal test-facing shapes. In real operation, you enqueue the SDK's own event types (e.g., `TaskStatusUpdateEvent`, `TaskArtifactUpdateEvent`). Replace these dataclasses with the SDK's types once you confirm the exact constructors on your installed version. Tests will need to be updated to match.
- **Docker on CI:** Tests never spawn a real container; all sandbox tests mock `asyncio.create_subprocess_exec`. `make shell-image` is only needed for live runs.
- **Discovery timing:** `scripts/run_all.sh` sleeps 1s before starting the orchestrator so specialist ports are open. If you see "discovery failed" warnings on startup, increase the sleep.
