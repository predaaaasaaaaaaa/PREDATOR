"""Process supervisor — mirrors OpenClaw's process supervision layer.

Manages the lifecycle of all spawned processes, handling:
- Process group management
- Graceful shutdown cascades
- Resource limit enforcement
- Background process notification
"""

from __future__ import annotations

import asyncio
import os
import signal
from typing import Optional

from predator.process.registry import ProcessRegistry, ProcessState, process_registry
from predator.utils.logger import get_logger

log = get_logger("process.supervisor")


class ProcessSupervisor:
    """Supervises all agent-spawned processes.

    Mirrors OpenClaw's getProcessSupervisor() pattern:
    - Tracks all child processes
    - Enforces cleanup on agent shutdown
    - Handles orphan detection
    - Manages background process notifications
    """

    def __init__(self, registry: Optional[ProcessRegistry] = None) -> None:
        self._registry = registry or process_registry
        self._shutdown = False
        self._cleanup_task: Optional[asyncio.Task] = None

    async def start(self) -> None:
        """Start the supervisor background monitoring."""
        self._shutdown = False
        self._cleanup_task = asyncio.create_task(self._monitor_loop())
        log.info("Process supervisor started")

    async def stop(self) -> None:
        """Stop the supervisor and kill all active processes."""
        self._shutdown = True
        if self._cleanup_task:
            self._cleanup_task.cancel()
            try:
                await self._cleanup_task
            except asyncio.CancelledError:
                pass

        # Kill remaining active processes
        for record in self._registry.active:
            try:
                os.killpg(os.getpgid(record.pid), signal.SIGTERM)
                log.info(f"Terminated process {record.pid}: {record.command[:80]}")
            except (ProcessLookupError, OSError):
                pass

        await asyncio.sleep(1)

        # Force kill stragglers
        for record in self._registry.active:
            try:
                os.killpg(os.getpgid(record.pid), signal.SIGKILL)
                self._registry.kill(record.pid)
            except (ProcessLookupError, OSError):
                pass

        log.info("Process supervisor stopped")

    async def _monitor_loop(self) -> None:
        """Background loop to monitor process health."""
        while not self._shutdown:
            try:
                for record in self._registry.active:
                    # Check if process is still alive
                    try:
                        os.kill(record.pid, 0)
                    except ProcessLookupError:
                        # Process died — mark as completed
                        self._registry.complete(record.pid, -1, "", "Process disappeared")
                        log.warning(f"Process {record.pid} disappeared: {record.command[:80]}")

                # Clean up old records
                self._registry.cleanup_completed(max_age=3600)

                await asyncio.sleep(5)
            except asyncio.CancelledError:
                break
            except Exception as e:
                log.error(f"Supervisor monitor error: {e}")
                await asyncio.sleep(10)

    @property
    def active_count(self) -> int:
        """Number of active processes."""
        return len(self._registry.active)

    def summary(self) -> dict:
        """Get a summary of process states."""
        records = self._registry.all_records
        return {
            "total": len(records),
            "running": sum(1 for r in records if r.state == ProcessState.RUNNING),
            "background": sum(1 for r in records if r.state == ProcessState.BACKGROUND),
            "completed": sum(1 for r in records if r.state == ProcessState.COMPLETED),
            "failed": sum(1 for r in records if r.state == ProcessState.FAILED),
            "killed": sum(1 for r in records if r.state == ProcessState.KILLED),
            "timed_out": sum(1 for r in records if r.state == ProcessState.TIMED_OUT),
        }
