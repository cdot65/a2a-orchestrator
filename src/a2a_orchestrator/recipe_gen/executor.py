from dataclasses import dataclass
from typing import Any

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

        except Exception as exc:  # noqa: BLE001
            log.exception("task_failed", task_id=context.task_id)
            await event_queue.enqueue_event(_StatusEvent("status", "failed", str(exc)))

    async def cancel(self, context, event_queue) -> None:
        log.info("task_cancelled", task_id=getattr(context, "task_id", "?"))
