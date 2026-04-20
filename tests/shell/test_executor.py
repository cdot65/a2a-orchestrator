import json
from unittest.mock import AsyncMock, patch

from a2a_orchestrator.shell.executor import ShellExecutor, build_card
from a2a_orchestrator.shell.sandbox import ShellResult


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


def test_build_card_reports_run_shell_skill():
    card = build_card("http://localhost:8003")
    assert card["name"] == "shell"
    assert card["skills"][0]["id"] == "run_shell"


async def test_executor_runs_command_and_returns_artifact():
    q = _FakeQueue()
    ctx = _Ctx("ls /work")
    fake = ShellResult(stdout="a\nb\n", stderr="", exit_code=0)

    with patch(
        "a2a_orchestrator.shell.executor.run_sandboxed",
        new=AsyncMock(return_value=fake),
    ):
        await ShellExecutor().execute(ctx, q)

    artifacts = [e for e in q.events if getattr(e, "kind", "") == "artifact"]
    assert artifacts
    data = json.loads(artifacts[0].text)
    assert data["stdout"] == "a\nb\n"
    assert data["exit_code"] == 0
    assert data["truncated_stdout"] is False

    statuses = [e.state for e in q.events if getattr(e, "kind", "") == "status"]
    assert statuses[-1] == "completed"


async def test_executor_streams_stdout_lines_as_text_parts():
    q = _FakeQueue()
    ctx = _Ctx("ls /work")

    async def _fake_run(command, *, on_line, timeout):
        await on_line("stdout", "line1\n")
        await on_line("stderr", "warn\n")
        return ShellResult(stdout="line1\n", stderr="warn\n", exit_code=0)

    with patch("a2a_orchestrator.shell.executor.run_sandboxed", side_effect=_fake_run):
        await ShellExecutor().execute(ctx, q)

    text_events = [e for e in q.events if getattr(e, "kind", "") == "text"]
    texts = [e.text for e in text_events]
    assert any("line1" in t for t in texts)
    assert any("[stderr]" in t for t in texts)


async def test_executor_reports_timeout():
    q = _FakeQueue()
    ctx = _Ctx("sleep 99")
    fake = ShellResult(stdout="", stderr="", exit_code=-1, timed_out=True)

    with patch(
        "a2a_orchestrator.shell.executor.run_sandboxed",
        new=AsyncMock(return_value=fake),
    ):
        await ShellExecutor().execute(ctx, q)

    artifacts = [e for e in q.events if getattr(e, "kind", "") == "artifact"]
    assert artifacts
    data = json.loads(artifacts[0].text)
    assert data["timed_out"] is True
    assert data["exit_code"] == -1


async def test_executor_fails_on_empty_command():
    q = _FakeQueue()
    ctx = _Ctx("   ")  # whitespace only

    await ShellExecutor().execute(ctx, q)

    statuses = [getattr(e, "state", None) for e in q.events]
    assert "failed" in statuses


async def test_executor_cancel_enqueues_cancelled_status():
    q = _FakeQueue()
    ctx = _Ctx("whatever")
    await ShellExecutor().cancel(ctx, q)
    statuses = [getattr(e, "state", None) for e in q.events]
    assert "cancelled" in statuses
