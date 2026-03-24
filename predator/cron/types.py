"""Cron system types — mirrors OpenClaw's cron/types.ts."""
from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Literal, Optional


class ScheduleKind(str, Enum):
    AT = "at"        # One-shot: ISO timestamp
    EVERY = "every"  # Fixed interval
    CRON = "cron"    # Cron expression


@dataclass
class CronSchedule:
    kind: ScheduleKind = ScheduleKind.EVERY
    # "at" fields
    at: str = ""                 # ISO timestamp
    # "every" fields
    every_ms: int = 0            # Interval in milliseconds
    anchor_ms: int = 0           # Anchor timestamp
    # "cron" fields
    expr: str = ""               # Cron expression (e.g., "*/5 * * * *")
    tz: str = ""                 # Timezone
    stagger_ms: int = 0          # Random stagger


class DeliveryMode(str, Enum):
    NONE = "none"
    ANNOUNCE = "announce"
    WEBHOOK = "webhook"


@dataclass
class CronDelivery:
    mode: DeliveryMode = DeliveryMode.NONE
    channel: str = ""
    to: str = ""
    webhook_url: str = ""


@dataclass
class CronPayload:
    kind: Literal["system_event", "agent_turn"] = "agent_turn"
    message: str = ""
    model: str = ""
    thinking: str = "low"
    timeout_seconds: int = 600
    deliver: bool = False
    channel: str = ""
    to: str = ""


@dataclass
class CronJobState:
    next_run_at_ms: float = 0
    running_at_ms: float = 0
    last_run_at_ms: float = 0
    last_status: str = ""          # "ok" | "error" | "skipped"
    last_error: str = ""
    last_duration_ms: float = 0
    consecutive_errors: int = 0


@dataclass
class CronJob:
    id: str = ""
    name: str = ""
    enabled: bool = True
    delete_after_run: bool = False
    schedule: CronSchedule = field(default_factory=CronSchedule)
    session_target: str = "main"   # "main" | "isolated"
    wake_mode: str = "next-heartbeat"  # "next-heartbeat" | "now"
    payload: CronPayload = field(default_factory=CronPayload)
    delivery: CronDelivery = field(default_factory=CronDelivery)
    state: CronJobState = field(default_factory=CronJobState)
