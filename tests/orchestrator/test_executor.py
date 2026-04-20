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

    statuses = [getattr(e, "state", None) for e in q.events]
    assert "failed" in statuses
