import re
from collections.abc import AsyncIterator
from dataclasses import dataclass

from a2a_orchestrator.common.claude import (
    call_with_schema,
    get_async_client,
    get_client,
    stream_text,
)

PLAN_SCHEMA = {
    "type": "object",
    "properties": {
        "steps": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "agent": {"type": "string"},
                    "skill": {"type": "string"},
                    "input": {"type": "string"},
                },
                "required": ["agent", "skill", "input"],
            },
        }
    },
    "required": ["steps"],
}

PLAN_SYSTEM = (
    "You are a planner. Given a user request and a list of available agents and their "
    "skills, return a sequential plan as a list of steps. Each step names an agent and "
    "skill from the capability list and provides a concrete input string for that "
    "skill. Use no agent not listed. Reference prior step output with "
    "{{step_N.output}} placeholders (N is 1-based). Empty steps list is fine if no "
    "agent is needed. Emit the plan via the emit_plan tool."
)

SYNTH_SYSTEM = (
    "You are a synthesizer. Given the user's original request and the outputs of each "
    "step, write a concise natural-language answer. If step outputs contain JSON, you "
    "may quote key fields. Do not repeat raw JSON wholesale."
)


@dataclass(frozen=True)
class PlanStep:
    agent: str
    skill: str
    input: str


def format_capabilities(cards: list[dict]) -> str:
    lines: list[str] = []
    for c in cards:
        lines.append(f"- {c['name']}: {c.get('description', '')}")
        for s in c.get("skills", []):
            ex = s.get("examples") or []
            ex_line = f" (e.g., {ex[0]})" if ex else ""
            lines.append(f"    - skill `{s['id']}` - {s.get('description', '')}{ex_line}")
    return "\n".join(lines) if lines else "(no agents available)"


def build_plan(user_request: str, cards: list[dict]) -> list[PlanStep]:
    caps = format_capabilities(cards)
    user_msg = f"User request:\n{user_request}\n\nAvailable agents:\n{caps}"
    raw = call_with_schema(
        get_client(),
        system=PLAN_SYSTEM,
        user=user_msg,
        tool_name="emit_plan",
        tool_description="Emit the sequential plan.",
        schema=PLAN_SCHEMA,
    )
    return [PlanStep(**s) for s in raw.get("steps", [])]


_PLACEHOLDER_RE = re.compile(r"\{\{step_(\d+)\.output\}\}")


def substitute_placeholders(text: str, outputs: dict[int, str]) -> str:
    def _repl(m: re.Match[str]) -> str:
        n = int(m.group(1))
        return outputs.get(n, m.group(0))

    return _PLACEHOLDER_RE.sub(_repl, text)


async def synthesize(user_request: str, *, step_outputs: dict[int, str]) -> AsyncIterator[str]:
    outputs_text = "\n\n".join(
        f"Step {n} output:\n{out}" for n, out in sorted(step_outputs.items())
    )
    user_msg = (
        f"Original request:\n{user_request}\n\n"
        f"{outputs_text if outputs_text else '(no steps were needed)'}"
    )
    async for chunk in stream_text(get_async_client(), system=SYNTH_SYSTEM, user=user_msg):
        yield chunk
