"""Heartbeat runner — mirrors OpenClaw's heartbeat system.

Priority-based wake queue, HEARTBEAT.md loading, active hours windowing.
"""
from __future__ import annotations

import asyncio
import logging
import os
import time
from dataclasses import dataclass, field
from enum import IntEnum
from typing import Any, Callable, Awaitable, Optional

logger = logging.getLogger(__name__)

HEARTBEAT_OK = "HEARTBEAT_OK"
DEFAULT_INTERVAL_MS = 30 * 60 * 1000  # 30 minutes
DEFAULT_COALESCE_MS = 250
DEFAULT_ACK_MAX_CHARS = 300


class WakePriority(IntEnum):
    RETRY = 0
    INTERVAL = 1
    DEFAULT = 2
    ACTION = 3


@dataclass
class WakeRequest:
    reason: str = ""
    priority: WakePriority = WakePriority.DEFAULT
    timestamp: float = 0.0


@dataclass
class HeartbeatConfig:
    interval_ms: int = DEFAULT_INTERVAL_MS
    model: str = ""
    target: str = "last"           # "last" | "none" | channel_id
    to: str = ""
    account_id: str = ""
    prompt: str = ""
    ack_max_chars: int = DEFAULT_ACK_MAX_CHARS
    active_hours_start: str = ""   # "09:00"
    active_hours_end: str = ""     # "22:00"
    active_hours_tz: str = ""


class HeartbeatRunner:
    """Priority-based heartbeat system."""

    def __init__(
        self,
        config: HeartbeatConfig | None = None,
        agent_handler: Optional[Callable[[str], Awaitable[str]]] = None,
        deliver_handler: Optional[Callable[[str, str], Awaitable[None]]] = None,
        workspace_dir: str = "",
    ):
        self._config = config or HeartbeatConfig()
        self._agent_handler = agent_handler
        self._deliver_handler = deliver_handler
        self._workspace_dir = workspace_dir
        self._wake_queue: list[WakeRequest] = []
        self._timer_task: Optional[asyncio.Task] = None
        self._running = False
        self._last_tick_at: float = 0
        self._consecutive_ok: int = 0

    def _load_heartbeat_md(self) -> str:
        """Load HEARTBEAT.md from workspace."""
        path = os.path.join(self._workspace_dir, "HEARTBEAT.md")
        if os.path.isfile(path):
            try:
                with open(path) as f:
                    content = f.read().strip()
                # Skip if empty (blank lines + headers only)
                lines = [l for l in content.split("\n") if l.strip() and not l.strip().startswith("#")]
                if not lines:
                    return ""
                return content
            except Exception:
                pass
        return ""

    def _is_active_hours(self) -> bool:
        """Check if current time is within active hours."""
        if not self._config.active_hours_start or not self._config.active_hours_end:
            return True
        try:
            from datetime import datetime, timezone as tz
            import zoneinfo
            zone = zoneinfo.ZoneInfo(self._config.active_hours_tz) if self._config.active_hours_tz else None
            now = datetime.now(zone)
            current = now.strftime("%H:%M")
            return self._config.active_hours_start <= current < self._config.active_hours_end
        except Exception:
            return True

    def _build_prompt(self, heartbeat_md: str) -> str:
        """Build the heartbeat prompt."""
        parts = []
        if self._config.prompt:
            parts.append(self._config.prompt)
        else:
            parts.append(
                "This is a scheduled heartbeat tick. Check your HEARTBEAT.md for pending tasks.\n"
                "If nothing needs attention, respond with HEARTBEAT_OK.\n"
                "If something needs attention, describe what you found WITHOUT including HEARTBEAT_OK."
            )
        if heartbeat_md:
            parts.append(f"\n--- HEARTBEAT.md ---\n{heartbeat_md}\n--- END ---")
        return "\n".join(parts)

    def wake(self, reason: str = "manual", priority: WakePriority = WakePriority.ACTION) -> None:
        """Queue a wake request."""
        self._wake_queue.append(WakeRequest(
            reason=reason, priority=priority, timestamp=time.time(),
        ))
        self._wake_queue.sort(key=lambda w: w.priority)

    async def start(self) -> None:
        self._running = True
        self._arm_timer()
        logger.info(f"Heartbeat started (interval: {self._config.interval_ms}ms)")

    async def stop(self) -> None:
        self._running = False
        if self._timer_task:
            self._timer_task.cancel()
            self._timer_task = None
        logger.info("Heartbeat stopped")

    def _arm_timer(self) -> None:
        if not self._running:
            return
        # Check wake queue first
        if self._wake_queue:
            delay_s = DEFAULT_COALESCE_MS / 1000
        else:
            delay_s = self._config.interval_ms / 1000

        if self._timer_task:
            self._timer_task.cancel()
        self._timer_task = asyncio.ensure_future(self._tick(delay_s))

    async def _tick(self, delay: float) -> None:
        await asyncio.sleep(delay)
        if not self._running:
            return

        # Active hours check
        if not self._is_active_hours():
            logger.debug("Heartbeat skipped: outside active hours")
            self._arm_timer()
            return

        # Drain wake queue
        wakes = list(self._wake_queue)
        self._wake_queue.clear()
        reason = wakes[0].reason if wakes else "interval"

        await self._execute_tick(reason)
        self._arm_timer()

    async def _execute_tick(self, reason: str) -> None:
        """Execute one heartbeat tick."""
        if not self._agent_handler:
            return

        heartbeat_md = self._load_heartbeat_md()
        prompt = self._build_prompt(heartbeat_md)

        logger.debug(f"Heartbeat tick: {reason}")
        self._last_tick_at = time.time()

        try:
            response = await self._agent_handler(prompt)
        except Exception as e:
            logger.error(f"Heartbeat agent error: {e}")
            self.wake("retry", WakePriority.RETRY)
            return

        # Check for HEARTBEAT_OK
        is_ok = HEARTBEAT_OK in response
        cleaned = response.replace(HEARTBEAT_OK, "").strip()

        if is_ok and len(cleaned) <= self._config.ack_max_chars:
            self._consecutive_ok += 1
            logger.debug(f"Heartbeat OK ({self._consecutive_ok} consecutive)")
            return

        # Alert — deliver to channel
        self._consecutive_ok = 0
        if self._deliver_handler and cleaned:
            try:
                target = self._config.target
                to = self._config.to
                await self._deliver_handler(cleaned, to)
                logger.info(f"Heartbeat alert delivered: {cleaned[:100]}")
            except Exception as e:
                logger.error(f"Heartbeat delivery failed: {e}")
