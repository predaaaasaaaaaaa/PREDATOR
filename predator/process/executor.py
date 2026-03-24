"""Process executor — mirrors OpenClaw's process/exec.ts and bash-tools.exec-runtime.ts.

Core subprocess execution with:
- PTY support for interactive tools
- Timeout management
- Output streaming and capture
- Background process support
- Security constraints (blocked env vars, command validation)
"""

from __future__ import annotations

import asyncio
import os
import signal
import subprocess
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import AsyncIterator, Callable, Optional

from predator.config.defaults import (
    DEFAULT_EXEC_TIMEOUT,
    DEFAULT_NO_OUTPUT_TIMEOUT,
    DEFAULT_OUTPUT_LIMIT,
)
from predator.process.registry import ProcessRegistry, process_registry
from predator.utils.logger import get_logger

log = get_logger("process.executor")


@dataclass
class ExecResult:
    """Result of a process execution."""

    exit_code: int
    stdout: str
    stderr: str
    pid: int
    elapsed: float
    timed_out: bool = False
    killed: bool = False
    command: str = ""


@dataclass
class ExecOptions:
    """Options for process execution — mirrors OpenClaw's exec schema."""

    command: str
    workdir: Optional[str] = None
    env: Optional[dict[str, str]] = None
    timeout: int = DEFAULT_EXEC_TIMEOUT
    no_output_timeout: int = DEFAULT_NO_OUTPUT_TIMEOUT
    output_limit: int = DEFAULT_OUTPUT_LIMIT
    background: bool = False
    pty: bool = False
    elevated: bool = False  # sudo
    tool_call_id: Optional[str] = None

    # Security
    blocked_env_vars: list[str] = field(default_factory=lambda: [
        "LD_PRELOAD", "LD_LIBRARY_PATH", "PYTHONPATH", "PYTHONHOME",
        "RUBYLIB", "PERL5LIB", "BASH_ENV", "ENV",
    ])


def _sanitize_env(
    env: Optional[dict[str, str]], blocked: list[str]
) -> dict[str, str]:
    """Create sanitized environment, removing blocked variables."""
    base = os.environ.copy()
    # Remove blocked vars
    for var in blocked:
        base.pop(var, None)
    # Apply user overrides
    if env:
        for key, value in env.items():
            if key not in blocked:
                base[key] = value
    return base


async def execute(
    opts: ExecOptions,
    on_output: Optional[Callable[[str], None]] = None,
    registry: Optional[ProcessRegistry] = None,
) -> ExecResult:
    """Execute a shell command asynchronously.

    Mirrors OpenClaw's runExecProcess() with:
    - Async subprocess management
    - Output streaming via callback
    - Timeout handling (total + no-output)
    - Output size limiting
    - Process registry tracking
    """
    if registry is None:
        registry = process_registry

    env = _sanitize_env(opts.env, opts.blocked_env_vars)
    cwd = opts.workdir or os.getcwd()

    # Build command
    cmd = opts.command
    if opts.elevated:
        cmd = f"sudo {cmd}"

    start_time = time.time()
    stdout_parts: list[str] = []
    stderr_parts: list[str] = []
    total_output_size = 0
    last_output_time = time.time()

    try:
        if opts.pty:
            result = await _execute_pty(cmd, cwd, env, opts, on_output)
            return result

        proc = await asyncio.create_subprocess_shell(
            cmd,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
            cwd=cwd,
            env=env,
            preexec_fn=os.setsid if hasattr(os, "setsid") else None,
        )

        pid = proc.pid or 0
        record = registry.register(
            pid=pid,
            command=opts.command,
            workdir=cwd,
            tool_call_id=opts.tool_call_id,
            is_background=opts.background,
        )

        # If background, return immediately
        if opts.background:
            return ExecResult(
                exit_code=-1,
                stdout=f"Process started in background (PID: {pid})",
                stderr="",
                pid=pid,
                elapsed=0.0,
                command=opts.command,
            )

        # Read output with timeouts
        timed_out = False
        killed = False

        async def read_stream(
            stream: asyncio.StreamReader, parts: list[str], is_stderr: bool = False
        ) -> None:
            nonlocal total_output_size, last_output_time
            while True:
                try:
                    line = await asyncio.wait_for(stream.readline(), timeout=1.0)
                except asyncio.TimeoutError:
                    # Check no-output timeout
                    if time.time() - last_output_time > opts.no_output_timeout:
                        return
                    continue

                if not line:
                    break

                decoded = line.decode("utf-8", errors="replace")
                last_output_time = time.time()

                if total_output_size < opts.output_limit:
                    parts.append(decoded)
                    total_output_size += len(decoded)

                    if on_output and not is_stderr:
                        on_output(decoded)

        try:
            await asyncio.wait_for(
                asyncio.gather(
                    read_stream(proc.stdout, stdout_parts),
                    read_stream(proc.stderr, stderr_parts, is_stderr=True),
                ),
                timeout=opts.timeout,
            )
            await proc.wait()
        except asyncio.TimeoutError:
            timed_out = True
            try:
                os.killpg(os.getpgid(pid), signal.SIGTERM)
                await asyncio.sleep(2)
                if proc.returncode is None:
                    os.killpg(os.getpgid(pid), signal.SIGKILL)
            except (ProcessLookupError, OSError):
                pass
            killed = True

        exit_code = proc.returncode or 0
        elapsed = time.time() - start_time
        stdout = "".join(stdout_parts)
        stderr = "".join(stderr_parts)

        # Update registry
        if timed_out:
            registry.timeout(pid)
        else:
            registry.complete(pid, exit_code, stdout[-2048:], stderr[-2048:])

        return ExecResult(
            exit_code=exit_code,
            stdout=stdout,
            stderr=stderr,
            pid=pid,
            elapsed=elapsed,
            timed_out=timed_out,
            killed=killed,
            command=opts.command,
        )

    except Exception as e:
        elapsed = time.time() - start_time
        log.error(f"Process execution failed: {e}")
        return ExecResult(
            exit_code=1,
            stdout="",
            stderr=str(e),
            pid=0,
            elapsed=elapsed,
            command=opts.command,
        )


async def _execute_pty(
    cmd: str,
    cwd: str,
    env: dict[str, str],
    opts: ExecOptions,
    on_output: Optional[Callable[[str], None]] = None,
) -> ExecResult:
    """Execute command in a pseudo-terminal (PTY).

    Required for interactive tools like vim, top, or tools that
    check for terminal capabilities.
    """
    import pty
    import select

    start_time = time.time()
    stdout_parts: list[str] = []

    master_fd, slave_fd = pty.openpty()

    proc = subprocess.Popen(
        cmd,
        shell=True,
        cwd=cwd,
        env=env,
        stdin=slave_fd,
        stdout=slave_fd,
        stderr=slave_fd,
        preexec_fn=os.setsid,
    )

    os.close(slave_fd)

    pid = proc.pid
    record = process_registry.register(
        pid=pid,
        command=opts.command,
        workdir=cwd,
        tool_call_id=opts.tool_call_id,
    )

    timed_out = False
    try:
        deadline = time.time() + opts.timeout
        last_output = time.time()

        while proc.poll() is None:
            if time.time() > deadline:
                timed_out = True
                break

            if time.time() - last_output > opts.no_output_timeout:
                timed_out = True
                break

            ready, _, _ = select.select([master_fd], [], [], 1.0)
            if ready:
                try:
                    data = os.read(master_fd, 4096)
                    if data:
                        decoded = data.decode("utf-8", errors="replace")
                        stdout_parts.append(decoded)
                        last_output = time.time()
                        if on_output:
                            on_output(decoded)
                except OSError:
                    break
    finally:
        os.close(master_fd)

    if timed_out:
        try:
            os.killpg(os.getpgid(pid), signal.SIGTERM)
            time.sleep(1)
            if proc.poll() is None:
                os.killpg(os.getpgid(pid), signal.SIGKILL)
        except (ProcessLookupError, OSError):
            pass
        process_registry.timeout(pid)
    else:
        process_registry.complete(pid, proc.returncode or 0, "".join(stdout_parts)[-2048:])

    return ExecResult(
        exit_code=proc.returncode or (1 if timed_out else 0),
        stdout="".join(stdout_parts),
        stderr="",
        pid=pid,
        elapsed=time.time() - start_time,
        timed_out=timed_out,
        command=opts.command,
    )


async def kill_process(pid: int) -> bool:
    """Kill a process by PID."""
    try:
        os.killpg(os.getpgid(pid), signal.SIGTERM)
        await asyncio.sleep(2)
        try:
            os.killpg(os.getpgid(pid), signal.SIGKILL)
        except ProcessLookupError:
            pass
        process_registry.kill(pid)
        return True
    except (ProcessLookupError, OSError):
        return False
