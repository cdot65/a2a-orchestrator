import json
from unittest.mock import MagicMock, patch

import httpx
import respx
from a2a.types import TaskArtifactUpdateEvent, TaskStatusUpdateEvent

from a2a_orchestrator.recipe_url.executor import RecipeUrlExecutor, build_card
from tests.conftest import get_state, get_text

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

    with (
        patch(
            "a2a_orchestrator.recipe_url.executor.call_with_schema",
            return_value=_payload(),
        ),
        patch("a2a_orchestrator.recipe_url.executor.get_client", return_value=MagicMock()),
    ):
        await RecipeUrlExecutor().execute(ctx, queue)

    artifact_events = [e for e in queue.events if isinstance(e, TaskArtifactUpdateEvent)]
    assert artifact_events
    data = json.loads(get_text(artifact_events[0]))
    assert data["source_url"] == SAMPLE_URL

    statuses = [get_state(e) for e in queue.events if isinstance(e, TaskStatusUpdateEvent)]
    assert statuses[-1] == "completed"


@respx.mock
async def test_executor_fails_on_bad_http_status():
    respx.get(SAMPLE_URL).mock(return_value=httpx.Response(404))
    queue = _FakeQueue()
    ctx = _FakeContext(SAMPLE_URL)

    await RecipeUrlExecutor().execute(ctx, queue)

    states = [get_state(e) for e in queue.events if isinstance(e, TaskStatusUpdateEvent)]
    assert "failed" in states


async def test_executor_fails_on_non_url_input():
    queue = _FakeQueue()
    ctx = _FakeContext("not a url")

    await RecipeUrlExecutor().execute(ctx, queue)

    states = [get_state(e) for e in queue.events if isinstance(e, TaskStatusUpdateEvent)]
    assert "failed" in states


@respx.mock
async def test_executor_fails_on_claude_validation_error():
    respx.get(SAMPLE_URL).mock(
        return_value=httpx.Response(200, text="<html><body>content</body></html>")
    )
    queue = _FakeQueue()
    ctx = _FakeContext(SAMPLE_URL)

    bad_payload = {"title": "x"}  # missing required fields

    with (
        patch(
            "a2a_orchestrator.recipe_url.executor.call_with_schema",
            return_value=bad_payload,
        ),
        patch("a2a_orchestrator.recipe_url.executor.get_client", return_value=MagicMock()),
    ):
        await RecipeUrlExecutor().execute(ctx, queue)

    states = [get_state(e) for e in queue.events if isinstance(e, TaskStatusUpdateEvent)]
    assert "failed" in states
    failed_event = next(
        e for e in queue.events if isinstance(e, TaskStatusUpdateEvent) and get_state(e) == "failed"
    )
    assert "schema" in get_text(failed_event).lower()


@respx.mock
async def test_executor_fails_on_claude_runtime_error():
    respx.get(SAMPLE_URL).mock(
        return_value=httpx.Response(200, text="<html><body>content</body></html>")
    )
    queue = _FakeQueue()
    ctx = _FakeContext(SAMPLE_URL)

    with (
        patch(
            "a2a_orchestrator.recipe_url.executor.call_with_schema",
            side_effect=RuntimeError("no tool_use"),
        ),
        patch("a2a_orchestrator.recipe_url.executor.get_client", return_value=MagicMock()),
    ):
        await RecipeUrlExecutor().execute(ctx, queue)

    states = [get_state(e) for e in queue.events if isinstance(e, TaskStatusUpdateEvent)]
    assert "failed" in states
    failed_event = next(
        e for e in queue.events if isinstance(e, TaskStatusUpdateEvent) and get_state(e) == "failed"
    )
    assert "structuring failed" in get_text(failed_event).lower()
