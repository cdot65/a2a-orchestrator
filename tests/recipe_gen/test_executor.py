import json
from unittest.mock import MagicMock, patch

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

    artifact_events = [e for e in queue.events if getattr(e, "kind", "") == "artifact"]
    assert artifact_events, "expected at least one artifact event"

    import os
    from pathlib import Path
    recipes_dir = Path(os.environ["RECIPES_DIR"])
    files = list(recipes_dir.glob("spicy-vegan-ramen-*.json"))
    assert len(files) == 1
    data = json.loads(files[0].read_text())
    assert data["title"] == "Spicy Vegan Ramen"

    statuses = [e.state for e in queue.events if getattr(e, "kind", "") == "status"]
    assert statuses[-1] == "completed"
    assert "working" in statuses


async def test_executor_fails_task_on_claude_error():
    queue = _FakeQueue()
    ctx = _FakeContext("A recipe")

    with patch(
        "a2a_orchestrator.recipe_gen.executor.call_with_schema",
        side_effect=RuntimeError("boom"),
    ), patch("a2a_orchestrator.recipe_gen.executor.get_client"):
        executor = RecipeGenExecutor()
        await executor.execute(ctx, queue)

    statuses = [getattr(e, "state", None) for e in queue.events if getattr(e, "state", None)]
    assert statuses.index("working") < statuses.index("failed")


async def test_executor_cancel_enqueues_cancelled_status():
    queue = _FakeQueue()
    ctx = _FakeContext("whatever")
    await RecipeGenExecutor().cancel(ctx, queue)
    statuses = [getattr(e, "state", None) for e in queue.events]
    assert "cancelled" in statuses
