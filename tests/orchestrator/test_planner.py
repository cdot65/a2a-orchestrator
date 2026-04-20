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
            {
                "id": skill_id,
                "name": skill_id,
                "description": f"{skill_id} skill",
                "examples": ["example input"],
            }
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
            {
                "agent": "recipe-url",
                "skill": "parse_recipe_url",
                "input": "https://example.com/ramen",
            }
        ]
    }
    with (
        patch(
            "a2a_orchestrator.orchestrator.planner.call_with_schema",
            return_value=fake,
        ),
        patch("a2a_orchestrator.orchestrator.planner.get_client", return_value=MagicMock()),
    ):
        steps = build_plan("fetch this: https://example.com/ramen", cards)
    assert len(steps) == 1
    assert steps[0] == PlanStep(
        agent="recipe-url", skill="parse_recipe_url", input="https://example.com/ramen"
    )


def test_build_plan_empty_is_fine():
    cards = [_card("recipe-url", "parse_recipe_url")]
    with (
        patch(
            "a2a_orchestrator.orchestrator.planner.call_with_schema",
            return_value={"steps": []},
        ),
        patch("a2a_orchestrator.orchestrator.planner.get_client", return_value=MagicMock()),
    ):
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

    with (
        patch(
            "a2a_orchestrator.orchestrator.planner.stream_text",
            return_value=_gen(),
        ),
        patch(
            "a2a_orchestrator.orchestrator.planner.get_async_client",
            return_value=_FakeAsyncClient(),
        ),
    ):
        chunks = []
        async for c in synthesize("q", step_outputs={1: "ok"}):
            chunks.append(c)
        assert "".join(chunks) == "Result: ok"
