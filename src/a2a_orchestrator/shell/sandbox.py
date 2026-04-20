import asyncio
import os
from collections.abc import Awaitable, Callable
from dataclasses import dataclass

_MAX_STREAM_BYTES = 1024 * 1024  # 1 MB per stream


@dataclass
class ShellResult:
    stdout: str
    stderr: str
    exit_code: int
    timed_out: bool = False
    truncated_stdout: bool = False
    truncated_stderr: bool = False


def _docker_cmd(command: str) -> list[str]:
    workspace = os.path.abspath(os.environ.get("WORKSPACE_DIR", "./workspace"))
    return [
        "docker",
        "run",
        "--rm",
        "--stop-timeout=0",
        "--network=none",
        "--read-only",
        "--cap-drop=ALL",
        "--security-opt=no-new-privileges",
        "--tmpfs",
        "/tmp:size=64m",
        "--memory=256m",
        "--cpus=0.5",
        "--pids-limit=64",
        "-v",
        f"{workspace}:/work:ro",
        "-w",
        "/work",
        "a2a-shell:latest",
        "sh",
        "-c",
        command,
    ]


async def _read_stream(
    stream,
    label: str,
    on_line: Callable[[str, str], Awaitable[None]] | None,
    buf: bytearray,
    limit: int,
) -> bool:
    truncated = False
    while True:
        line = await stream.readline()
        if not line:
            break
        if len(buf) < limit:
            room = limit - len(buf)
            buf.extend(line[:room])
            if len(line) > room:
                truncated = True
        else:
            truncated = True
        if on_line:
            try:
                await on_line(label, line.decode("utf-8", errors="replace"))
            except Exception:  # noqa: BLE001
                pass
    return truncated


async def run_sandboxed(
    command: str,
    *,
    on_line: Callable[[str, str], Awaitable[None]] | None = None,
    timeout: float = 30.0,
) -> ShellResult:
    proc = await asyncio.create_subprocess_exec(
        *_docker_cmd(command),
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE,
    )

    stdout_buf = bytearray()
    stderr_buf = bytearray()

    async def _run():
        out_trunc, err_trunc = await asyncio.gather(
            _read_stream(proc.stdout, "stdout", on_line, stdout_buf, _MAX_STREAM_BYTES),
            _read_stream(proc.stderr, "stderr", on_line, stderr_buf, _MAX_STREAM_BYTES),
        )
        rc = await proc.wait()
        return rc, out_trunc, err_trunc

    try:
        rc, out_trunc, err_trunc = await asyncio.wait_for(_run(), timeout=timeout)
    except TimeoutError:
        proc.kill()
        try:
            await proc.wait()
        except Exception:  # noqa: BLE001
            pass
        return ShellResult(
            stdout=stdout_buf.decode("utf-8", errors="replace"),
            stderr=stderr_buf.decode("utf-8", errors="replace"),
            exit_code=-1,
            timed_out=True,
        )

    return ShellResult(
        stdout=stdout_buf.decode("utf-8", errors="replace"),
        stderr=stderr_buf.decode("utf-8", errors="replace"),
        exit_code=rc,
        truncated_stdout=out_trunc,
        truncated_stderr=err_trunc,
    )


def docker_available() -> bool:
    import subprocess

    try:
        subprocess.run(
            ["docker", "info"],
            check=True,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            timeout=5,
        )
        return True
    except Exception:  # noqa: BLE001
        return False
