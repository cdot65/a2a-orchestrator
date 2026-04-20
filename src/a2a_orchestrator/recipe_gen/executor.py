from typing import Any

from a2a.types import TaskState
from pydantic import ValidationError

from a2a_orchestrator.common.a2a_helpers import artifact_event, status_event
from a2a_orchestrator.common.claude import call_with_schema, get_client
from a2a_orchestrator.common.logging import get_logger
from a2a_orchestrator.common.persistence import save_recipe
from a2a_orchestrator.common.recipe import Recipe, recipe_json_schema

log = get_logger("recipe-gen")

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
        await event_queue.enqueue_event(
            status_event(
                task_id=context.task_id,
                context_id=context.context_id,
                state=TaskState.working,
                message="generating recipe",
            )
        )

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
            try:
                recipe = Recipe(**raw)
            except ValidationError as ve:
                log.warning("recipe_validation_failed", errors=ve.errors(), task_id=context.task_id)
                await event_queue.enqueue_event(
                    status_event(
                        task_id=context.task_id,
                        context_id=context.context_id,
                        state=TaskState.failed,
                        message="generated recipe did not match schema",
                        final=True,
                    )
                )
                return

            try:
                paths = save_recipe(recipe)
            except OSError as e:
                log.warning("persist_failed", error=str(e), task_id=context.task_id)
                await event_queue.enqueue_event(
                    status_event(
                        task_id=context.task_id,
                        context_id=context.context_id,
                        state=TaskState.failed,
                        message=f"persist failed: {e}",
                        final=True,
                    )
                )
                return

            log.info(
                "recipe_saved",
                task_id=context.task_id,
                json=str(paths.json_path),
                md=str(paths.md_path),
            )

            await event_queue.enqueue_event(
                artifact_event(
                    task_id=context.task_id,
                    context_id=context.context_id,
                    mime_type="application/json",
                    text=recipe.model_dump_json(),
                )
            )
            await event_queue.enqueue_event(
                status_event(
                    task_id=context.task_id,
                    context_id=context.context_id,
                    state=TaskState.completed,
                    final=True,
                )
            )
            log.info("task_completed", task_id=context.task_id)

        except Exception as exc:  # noqa: BLE001
            log.exception("task_failed", task_id=context.task_id)
            await event_queue.enqueue_event(
                status_event(
                    task_id=context.task_id,
                    context_id=context.context_id,
                    state=TaskState.failed,
                    message=str(exc),
                    final=True,
                )
            )

    async def cancel(self, context, event_queue) -> None:
        log.info("task_cancelled", task_id=getattr(context, "task_id", "?"))
        await event_queue.enqueue_event(
            status_event(
                task_id=getattr(context, "task_id", ""),
                context_id=getattr(context, "context_id", ""),
                state=TaskState.canceled,
                final=True,
            )
        )
