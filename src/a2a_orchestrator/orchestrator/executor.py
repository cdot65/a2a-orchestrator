import os
from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from typing import Any

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
    from a2a.types import Message, TextPart

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
    async def execute(self, context: Any, event_queue: Any) -> None:
        user_text = context.get_user_input()
        log.info("task_started", task_id=context.task_id, prompt=user_text[:160])

        await event_queue.enqueue_event(_StatusEvent("status", "working", "discovering"))
        ports = [
            int(p)
            for p in os.environ.get("A2A_DISCOVERY_PORTS", "8001,8002,8003").split(",")
            if p.strip()
        ]
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
            if plan
            else "Plan: (none — synthesizing directly)"
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

            async def _on_event(pair: tuple[str, str]) -> None:  # noqa: B023
                _label, text = pair
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

    async def cancel(self, context: Any, event_queue: Any) -> None:
        log.info("task_cancelled")
        await event_queue.enqueue_event(_StatusEvent("status", "cancelled"))
