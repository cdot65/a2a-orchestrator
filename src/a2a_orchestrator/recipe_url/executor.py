from typing import Any

import httpx
from a2a.types import TaskState
from pydantic import ValidationError

from a2a_orchestrator.common.a2a_helpers import artifact_event, status_event
from a2a_orchestrator.common.claude import call_with_schema, get_client
from a2a_orchestrator.common.logging import get_logger
from a2a_orchestrator.common.persistence import save_recipe
from a2a_orchestrator.common.recipe import Recipe, recipe_json_schema
from a2a_orchestrator.recipe_url.extract import extract_main_text

log = get_logger("recipe-url")

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
                status_event(
                    task_id=context.task_id,
                    context_id=context.context_id,
                    state=TaskState.failed,
                    message="input must be an http(s) URL",
                    final=True,
                )
            )
            return

        await event_queue.enqueue_event(
            status_event(
                task_id=context.task_id,
                context_id=context.context_id,
                state=TaskState.working,
                message="fetching",
            )
        )
        try:
            async with httpx.AsyncClient(timeout=20.0, follow_redirects=True) as client:
                resp = await client.get(user_text)
                resp.raise_for_status()
                html = resp.text
        except httpx.HTTPError as e:
            log.warning("fetch_failed", url=user_text, error=str(e))
            await event_queue.enqueue_event(
                status_event(
                    task_id=context.task_id,
                    context_id=context.context_id,
                    state=TaskState.failed,
                    message=f"fetch failed: {e}",
                    final=True,
                )
            )
            return

        await event_queue.enqueue_event(
            status_event(
                task_id=context.task_id,
                context_id=context.context_id,
                state=TaskState.working,
                message="extracting",
            )
        )
        text = extract_main_text(html)

        await event_queue.enqueue_event(
            status_event(
                task_id=context.task_id,
                context_id=context.context_id,
                state=TaskState.working,
                message="structuring",
            )
        )
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
        except ValidationError as e:
            log.warning("structure_validation_failed", errors=e.errors())
            await event_queue.enqueue_event(
                status_event(
                    task_id=context.task_id,
                    context_id=context.context_id,
                    state=TaskState.failed,
                    message="structured recipe did not match schema",
                    final=True,
                )
            )
            return
        except RuntimeError as e:
            log.warning("structure_failed", error=str(e))
            await event_queue.enqueue_event(
                status_event(
                    task_id=context.task_id,
                    context_id=context.context_id,
                    state=TaskState.failed,
                    message=f"structuring failed: {e}",
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

        log.info("recipe_saved", task_id=context.task_id, json=str(paths.json_path))
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
