import asyncio
from unittest.mock import AsyncMock, MagicMock, patch

from a2a_orchestrator.shell.sandbox import ShellResult, run_sandboxed


async def _fake_proc(stdout: bytes, stderr: bytes, returncode: int):
    proc = MagicMock()
    proc.returncode = returncode

    stdout_lines = stdout.splitlines(keepends=True) or [b""]
    stderr_lines = stderr.splitlines(keepends=True) or [b""]

    def _readline_factory(lines):
        # Wrap the end with b"" so the consumer loop breaks cleanly
        queue = lines + [b""]
        idx = {"i": 0}

        async def _readline():
            i = idx["i"]
            if i >= len(queue):
                return b""
            idx["i"] = i + 1
            return queue[i]

        return _readline

    proc.stdout = MagicMock()
    proc.stdout.readline = _readline_factory(stdout_lines)
    proc.stderr = MagicMock()
    proc.stderr.readline = _readline_factory(stderr_lines)
    proc.wait = AsyncMock(return_value=returncode)
    proc.kill = MagicMock()
    return proc


async def test_run_sandboxed_collects_stdout_and_exit_code():
    async def _create(*args, **kwargs):
        return await _fake_proc(b"hello\n", b"", 0)

    lines: list[tuple[str, str]] = []

    async def _on_line(stream: str, line: str):
        lines.append((stream, line))

    with patch("asyncio.create_subprocess_exec", side_effect=_create):
        result = await run_sandboxed("echo hello", on_line=_on_line, timeout=5)

    assert isinstance(result, ShellResult)
    assert result.exit_code == 0
    assert "hello" in result.stdout
    assert ("stdout", "hello\n") in lines


async def test_run_sandboxed_times_out():
    async def _hang(*args, **kwargs):
        proc = MagicMock()
        proc.returncode = None
        proc.stdout = MagicMock()
        proc.stdout.readline = AsyncMock(return_value=b"")
        proc.stderr = MagicMock()
        proc.stderr.readline = AsyncMock(return_value=b"")

        async def _wait():
            await asyncio.sleep(10)
            return 0

        proc.wait = AsyncMock(side_effect=_wait)
        proc.kill = MagicMock()
        return proc

    with patch("asyncio.create_subprocess_exec", side_effect=_hang):
        result = await run_sandboxed("sleep 9", on_line=None, timeout=0.2)

    assert result.exit_code == -1
    assert result.timed_out is True


async def test_run_sandboxed_truncates_large_output():
    big = b"x" * (2 * 1024 * 1024) + b"\n"

    async def _create(*args, **kwargs):
        return await _fake_proc(big, b"", 0)

    with patch("asyncio.create_subprocess_exec", side_effect=_create):
        result = await run_sandboxed("cat big", on_line=None, timeout=5)

    assert len(result.stdout) <= 1024 * 1024
    assert result.truncated_stdout is True
