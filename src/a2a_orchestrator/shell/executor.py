import json
from dataclasses import dataclass
from typing import Any

from a2a_orchestrator.common.logging import get_logger
from a2a_orchestrator.shell.sandbox import run_sandboxed

log = get_logger("shell")


@dataclass
class _StatusEvent:
    kind: str
    state: str
    message: str = ""


@dataclass
class _TextEvent:
    kind: str  # "text"
    text: str


@dataclass
class _ArtifactEvent:
    kind: str  # "artifact"
    mime_type: str
    text: str


def build_card(url: str) -> dict[str, Any]:
    from a2a_orchestrator.common.a2a_helpers import build_agent_card

    return build_agent_card(
        name="shell",
        description="Run a sandboxed shell command in a read-only workspace.",
        url=url,
        skills=[
            {
                "id": "run_shell",
                "name": "run_shell",
                "description": "Run a shell command in a sandboxed container. "
                "Read-only workspace at /work. 30s timeout.",
                "tags": ["shell", "sandbox"],
                "examples": ["ls /work", "grep -r 'ramen' /work/recipes"],
            }
        ],
    )


class ShellExecutor:
    async def execute(self, context, event_queue) -> None:
        command = context.get_user_input().strip()
        log.info("task_started", task_id=context.task_id, command=command[:200])

        if not command:
            await event_queue.enqueue_event(_StatusEvent("status", "failed", "empty command"))
            return

        await event_queue.enqueue_event(_StatusEvent("status", "working", f"running: {command}"))

        async def _on_line(stream: str, line: str) -> None:
            prefix = "" if stream == "stdout" else "[stderr] "
            await event_queue.enqueue_event(_TextEvent("text", f"{prefix}{line.rstrip()}"))

        result = await run_sandboxed(command, on_line=_on_line, timeout=30.0)

        payload = {
            "stdout": result.stdout,
            "stderr": result.stderr,
            "exit_code": result.exit_code,
            "timed_out": result.timed_out,
            "truncated_stdout": result.truncated_stdout,
            "truncated_stderr": result.truncated_stderr,
        }
        await event_queue.enqueue_event(
            _ArtifactEvent("artifact", "application/json", json.dumps(payload))
        )
        await event_queue.enqueue_event(_StatusEvent("status", "completed"))
        log.info("task_completed", task_id=context.task_id, exit_code=result.exit_code)

    async def cancel(self, context, event_queue) -> None:
        log.info("task_cancelled", task_id=getattr(context, "task_id", "?"))
        await event_queue.enqueue_event(_StatusEvent("status", "cancelled"))
