"""Process registry — mirrors OpenClaw's bash-process-registry.ts.

Tracks all active and completed processes spawned by the agent.
"""

from __future__ import annotations

import time
from dataclasses import dataclass, field
from typing import Optional
from enum import Enum


class ProcessState(str, Enum):
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"
    KILLED = "killed"
    TIMED_OUT = "timed_out"
    BACKGROUND = "background"


@dataclass
class ProcessRecord:
    """A tracked process."""

    pid: int
    command: str
    started_at: float = field(default_factory=time.time)
    ended_at: Optional[float] = None
    state: ProcessState = ProcessState.RUNNING
    exit_code: Optional[int] = None
    stdout_tail: str = ""
    stderr_tail: str = ""
    is_background: bool = False
    workdir: Optional[str] = None
    tool_call_id: Optional[str] = None

    @property
    def elapsed(self) -> float:
        end = self.ended_at or time.time()
        return end - self.started_at

    @property
    def is_active(self) -> bool:
        return self.state in (ProcessState.RUNNING, ProcessState.BACKGROUND)


class ProcessRegistry:
    """Registry of all processes spawned by the agent.

    Mirrors OpenClaw's ProcessSession tracking with:
    - Active process listing
    - Background process management
    - Output tail capture
    - Process lifecycle tracking
    """

    def __init__(self) -> None:
        self._processes: dict[int, ProcessRecord] = {}
        self._next_id: int = 1

    def register(
        self,
        pid: int,
        command: str,
        workdir: Optional[str] = None,
        tool_call_id: Optional[str] = None,
        is_background: bool = False,
    ) -> ProcessRecord:
        """Register a new process."""
        record = ProcessRecord(
            pid=pid,
            command=command,
            workdir=workdir,
            tool_call_id=tool_call_id,
            is_background=is_background,
            state=ProcessState.BACKGROUND if is_background else ProcessState.RUNNING,
        )
        self._processes[pid] = record
        return record

    def complete(
        self,
        pid: int,
        exit_code: int,
        stdout_tail: str = "",
        stderr_tail: str = "",
    ) -> Optional[ProcessRecord]:
        """Mark a process as completed."""
        record = self._processes.get(pid)
        if record:
            record.state = ProcessState.COMPLETED if exit_code == 0 else ProcessState.FAILED
            record.exit_code = exit_code
            record.ended_at = time.time()
            record.stdout_tail = stdout_tail[-2048:]  # Keep last 2KB
            record.stderr_tail = stderr_tail[-2048:]
        return record

    def kill(self, pid: int) -> Optional[ProcessRecord]:
        """Mark a process as killed."""
        record = self._processes.get(pid)
        if record:
            record.state = ProcessState.KILLED
            record.ended_at = time.time()
        return record

    def timeout(self, pid: int) -> Optional[ProcessRecord]:
        """Mark a process as timed out."""
        record = self._processes.get(pid)
        if record:
            record.state = ProcessState.TIMED_OUT
            record.ended_at = time.time()
        return record

    def get(self, pid: int) -> Optional[ProcessRecord]:
        """Get a process record by PID."""
        return self._processes.get(pid)

    @property
    def active(self) -> list[ProcessRecord]:
        """Get all active (running/background) processes."""
        return [p for p in self._processes.values() if p.is_active]

    @property
    def all_records(self) -> list[ProcessRecord]:
        """Get all process records."""
        return list(self._processes.values())

    def cleanup_completed(self, max_age: float = 3600) -> int:
        """Remove completed process records older than max_age seconds."""
        now = time.time()
        to_remove = [
            pid
            for pid, record in self._processes.items()
            if not record.is_active and record.ended_at and now - record.ended_at > max_age
        ]
        for pid in to_remove:
            del self._processes[pid]
        return len(to_remove)


# Global process registry
process_registry = ProcessRegistry()
