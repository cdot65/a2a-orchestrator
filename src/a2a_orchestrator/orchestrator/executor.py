import os
from collections.abc import Awaitable, Callable
from typing import Any

from a2a.types import TaskArtifactUpdateEvent, TaskState, TaskStatusUpdateEvent

from a2a_orchestrator.common.a2a_helpers import (
    build_agent_card,
    discover_agents,
    status_event,
    text_update,
)
from a2a_orchestrator.common.logging import get_logger
from a2a_orchestrator.orchestrator.planner import (
    PlanStep,
    build_plan,
    substitute_placeholders,
    synthesize,
)

log = get_logger("orchestrator")


def build_card(url: str) -> dict[str, Any]:
    return build_agent_card(
        name="orchestrator",
        description="Plan, dispatch, and synthesize across specialist agents.",
        url=url,
        skills=[
            {
                "id": "orchestrate",
                "name": "orchestrate",
                "description": (
                    "Accept a freeform request, plan with specialist agents,"
                    " return a synthesized answer."
                ),
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
    """Call a child agent via A2A streaming, forward events, return final artifact text."""
    import httpx
    from a2a.client import A2AClient
    from a2a.types import (
        JSONRPCErrorResponse,
        Message,
        MessageSendParams,
        Role,
        SendStreamingMessageRequest,
        TextPart,
    )

    async with httpx.AsyncClient(timeout=None) as http:
        client = A2AClient(httpx_client=http, url=agent_url)
        message = Message(
            role=Role.user,
            parts=[TextPart(text=input_text)],
            message_id=os.urandom(8).hex(),
        )
        request = SendStreamingMessageRequest(
            id=os.urandom(8).hex(),
            params=MessageSendParams(message=message),
        )

        final_artifact_text = ""
        terminal_non_completed = {"canceled", "rejected", "input-required", "auth-required"}

        async for wrapper in client.send_message_streaming(request):
            if isinstance(wrapper.root, JSONRPCErrorResponse):
                raise RuntimeError(f"{skill} RPC error: {wrapper.root.error}")
            event = wrapper.root.result

            if isinstance(event, TaskStatusUpdateEvent):
                status = event.status
                state_val = status.state
                state_str = state_val.value if hasattr(state_val, "value") else str(state_val)
                msg_text = _message_to_text(status.message) if status.message is not None else ""
                await on_event(("text", f"[{skill}] {state_str}: {msg_text}".rstrip(": ")))
                if state_str == "failed":
                    raise RuntimeError(f"{skill} failed: {msg_text}")
                if state_str in terminal_non_completed:
                    raise RuntimeError(f"{skill} ended in terminal state {state_str}: {msg_text}")
            elif isinstance(event, TaskArtifactUpdateEvent):
                parts = event.artifact.parts
                for p in parts:
                    p_root = getattr(p, "root", p)
                    t = getattr(p_root, "text", None)
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


def _message_to_text(msg) -> str:
    parts = getattr(msg, "parts", [])
    pieces = []
    for p in parts:
        p_root = getattr(p, "root", p)
        t = getattr(p_root, "text", None)
        if t:
            pieces.append(t)
    return " ".join(pieces)


class OrchestratorExecutor:
    async def execute(self, context: Any, event_queue: Any) -> None:
        user_text = context.get_user_input()
        log.info("task_started", task_id=context.task_id, prompt=user_text[:160])

        await event_queue.enqueue_event(
            status_event(
                task_id=context.task_id,
                context_id=context.context_id,
                state=TaskState.working,
                message="discovering",
            )
        )
        ports = [
            int(p)
            for p in os.environ.get("A2A_DISCOVERY_PORTS", "8001,8002,8003").split(",")
            if p.strip()
        ]
        cards = await discover_agents(ports)
        log.info("discovery", task_id=context.task_id, agents=[c["name"] for c in cards])

        await event_queue.enqueue_event(
            status_event(
                task_id=context.task_id,
                context_id=context.context_id,
                state=TaskState.working,
                message="planning",
            )
        )
        try:
            plan: list[PlanStep] = build_plan(user_text, cards)
        except Exception as e:  # noqa: BLE001
            log.exception("plan_failed")
            await event_queue.enqueue_event(
                status_event(
                    task_id=context.task_id,
                    context_id=context.context_id,
                    state=TaskState.failed,
                    message=f"plan: {e}",
                    final=True,
                )
            )
            return

        plan_summary = (
            "Plan: " + "; ".join(f"{i + 1}) {s.agent}:{s.skill}" for i, s in enumerate(plan))
            if plan
            else "Plan: (none — synthesizing directly)"
        )
        await event_queue.enqueue_event(
            text_update(
                task_id=context.task_id,
                context_id=context.context_id,
                text=plan_summary,
            )
        )

        step_outputs: dict[int, str] = {}
        for idx, step in enumerate(plan, start=1):
            agent_card = next((c for c in cards if c["name"] == step.agent), None)
            if not agent_card:
                await event_queue.enqueue_event(
                    status_event(
                        task_id=context.task_id,
                        context_id=context.context_id,
                        state=TaskState.failed,
                        message=f"unknown agent {step.agent}",
                        final=True,
                    )
                )
                return
            resolved_input = substitute_placeholders(step.input, step_outputs)

            async def _on_event(pair: tuple[str, str]) -> None:  # noqa: B023
                _label, text = pair
                await event_queue.enqueue_event(
                    text_update(
                        task_id=context.task_id,
                        context_id=context.context_id,
                        text=text,
                    )
                )

            try:
                output = await dispatch_step(
                    agent_card["url"], step.skill, resolved_input, _on_event
                )
            except Exception as e:  # noqa: BLE001
                log.exception("step_failed", step=idx)
                await event_queue.enqueue_event(
                    status_event(
                        task_id=context.task_id,
                        context_id=context.context_id,
                        state=TaskState.failed,
                        message=f"step {idx}: {e}",
                        final=True,
                    )
                )
                return
            step_outputs[idx] = output

        await event_queue.enqueue_event(
            status_event(
                task_id=context.task_id,
                context_id=context.context_id,
                state=TaskState.working,
                message="synthesizing",
            )
        )
        try:
            async for chunk in synthesize(user_text, step_outputs=step_outputs):
                await event_queue.enqueue_event(
                    text_update(
                        task_id=context.task_id,
                        context_id=context.context_id,
                        text=chunk,
                    )
                )
        except Exception as e:  # noqa: BLE001
            log.exception("synthesis_failed")
            await event_queue.enqueue_event(
                status_event(
                    task_id=context.task_id,
                    context_id=context.context_id,
                    state=TaskState.failed,
                    message=f"synthesis: {e}",
                    final=True,
                )
            )
            return

        await event_queue.enqueue_event(
            status_event(
                task_id=context.task_id,
                context_id=context.context_id,
                state=TaskState.completed,
                final=True,
            )
        )
        log.info("task_completed", task_id=context.task_id)

    async def cancel(self, context: Any, event_queue: Any) -> None:
        log.info("task_cancelled")
        await event_queue.enqueue_event(
            status_event(
                task_id=context.task_id,
                context_id=context.context_id,
                state=TaskState.canceled,
                final=True,
            )
        )
