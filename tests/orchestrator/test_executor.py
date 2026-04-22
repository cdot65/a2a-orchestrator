from unittest.mock import AsyncMock, patch

from a2a.types import TaskStatusUpdateEvent

from a2a_orchestrator.orchestrator.executor import OrchestratorExecutor, build_card
from a2a_orchestrator.orchestrator.planner import PlanStep
from tests.conftest import get_state, get_text


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


async def test_executor_plans_dispatches_synthesizes():
    cards = [_card("recipe-url", 8001, "parse_recipe_url")]
    plan = [PlanStep(agent="recipe-url", skill="parse_recipe_url", input="https://x/y")]

    async def _fake_dispatch(agent_url, skill, text, on_event):
        await on_event(("text", "[recipe-url] working: fetching"))
        return '{"title":"X"}'

    async def _fake_synth(*args, **kwargs):
        for c in ["done: ", "X"]:
            yield c

    q = _FakeQueue()

    with (
        patch(
            "a2a_orchestrator.orchestrator.executor.discover_agents",
            new=AsyncMock(return_value=cards),
        ),
        patch(
            "a2a_orchestrator.orchestrator.executor.build_plan",
            return_value=plan,
        ),
        patch(
            "a2a_orchestrator.orchestrator.executor.dispatch_step",
            side_effect=_fake_dispatch,
        ),
        patch(
            "a2a_orchestrator.orchestrator.executor.synthesize",
            side_effect=_fake_synth,
        ),
    ):
        await OrchestratorExecutor().execute(_Ctx("scrape https://x/y"), q)

    texts = [get_text(e) for e in q.events if isinstance(e, TaskStatusUpdateEvent)]
    assert any(t and "Plan:" in t for t in texts)
    assert any(t and "[recipe-url]" in t for t in texts)
    assert any(t and ("done: " in t or "X" in t) for t in texts)
    states = [get_state(e) for e in q.events if isinstance(e, TaskStatusUpdateEvent)]
    assert states[-1] == "completed"


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

    with (
        patch(
            "a2a_orchestrator.orchestrator.executor.discover_agents",
            new=AsyncMock(return_value=cards),
        ),
        patch(
            "a2a_orchestrator.orchestrator.executor.build_plan",
            return_value=plan,
        ),
        patch(
            "a2a_orchestrator.orchestrator.executor.dispatch_step",
            side_effect=_fake_dispatch,
        ),
        patch(
            "a2a_orchestrator.orchestrator.executor.synthesize",
            side_effect=_fake_synth,
        ),
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

    with (
        patch(
            "a2a_orchestrator.orchestrator.executor.discover_agents",
            new=AsyncMock(return_value=cards),
        ),
        patch(
            "a2a_orchestrator.orchestrator.executor.build_plan",
            return_value=plan,
        ),
        patch(
            "a2a_orchestrator.orchestrator.executor.dispatch_step",
            side_effect=_fake_dispatch,
        ),
    ):
        await OrchestratorExecutor().execute(_Ctx("go"), q)

    states = [get_state(e) for e in q.events if isinstance(e, TaskStatusUpdateEvent)]
    assert "failed" in states


async def test_executor_replays_context_history_on_repeat_calls(monkeypatch):
    """Second call with the same context_id should see prior turn in planner input."""
    from a2a_orchestrator.orchestrator import executor as ex

    monkeypatch.setattr(ex, "_HISTORY", {})

    cards = [_card("recipe-gen", 8002, "generate_recipe")]

    captured_inputs: list[str] = []

    def _fake_build_plan(user_request, _cards):
        captured_inputs.append(user_request)
        return [PlanStep(agent="recipe-gen", skill="generate_recipe", input="x")]

    async def _fake_dispatch(agent_url, skill, text, on_event):
        return '{"title":"X"}'

    async def _fake_synth(q, *, step_outputs):
        for c in ["answer-", q[:20]]:
            yield c

    class _CtxWithId:
        def __init__(self, text: str, context_id: str):
            self.task_id = "t-" + context_id
            self.context_id = context_id
            self._t = text

        def get_user_input(self) -> str:
            return self._t

    with (
        patch(
            "a2a_orchestrator.orchestrator.executor.discover_agents",
            new=AsyncMock(return_value=cards),
        ),
        patch(
            "a2a_orchestrator.orchestrator.executor.build_plan",
            side_effect=_fake_build_plan,
        ),
        patch(
            "a2a_orchestrator.orchestrator.executor.dispatch_step",
            side_effect=_fake_dispatch,
        ),
        patch(
            "a2a_orchestrator.orchestrator.executor.synthesize",
            side_effect=_fake_synth,
        ),
    ):
        # Turn 1: no history yet
        await OrchestratorExecutor().execute(_CtxWithId("My name is Ada.", "ctx-1"), _FakeQueue())
        # Turn 2: same context_id, planner should see prior transcript
        await OrchestratorExecutor().execute(_CtxWithId("What's my name?", "ctx-1"), _FakeQueue())
        # Turn 3: different context_id, should NOT see ctx-1 history
        await OrchestratorExecutor().execute(_CtxWithId("Hello", "ctx-2"), _FakeQueue())

    # Turn 1: no prior history
    assert captured_inputs[0] == "My name is Ada."
    # Turn 2: prior user + assistant turn + new user message in transcript
    assert "USER: My name is Ada." in captured_inputs[1]
    assert "ASSISTANT:" in captured_inputs[1]
    assert "USER: What's my name?" in captured_inputs[1]
    # Turn 3: different context — no history
    assert captured_inputs[2] == "Hello"
