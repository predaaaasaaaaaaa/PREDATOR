"""Cron schedule computation — mirrors OpenClaw's cron/schedule.ts."""
from __future__ import annotations

import re
import time
from datetime import datetime, timezone

from predator.cron.types import CronSchedule, ScheduleKind


def compute_next_run(schedule: CronSchedule, now_ms: float | None = None) -> float:
    """Compute next run time in milliseconds since epoch."""
    if now_ms is None:
        now_ms = time.time() * 1000

    if schedule.kind == ScheduleKind.AT:
        dt = datetime.fromisoformat(schedule.at.replace("Z", "+00:00"))
        return dt.timestamp() * 1000

    if schedule.kind == ScheduleKind.EVERY:
        if schedule.every_ms <= 0:
            return now_ms + 60_000
        anchor = schedule.anchor_ms or now_ms
        elapsed = now_ms - anchor
        intervals = int(elapsed / schedule.every_ms) + 1
        return anchor + intervals * schedule.every_ms

    if schedule.kind == ScheduleKind.CRON:
        try:
            from croniter import croniter
            now_dt = datetime.fromtimestamp(now_ms / 1000, tz=timezone.utc)
            cron = croniter(schedule.expr, now_dt)
            next_dt = cron.get_next(datetime)
            result = next_dt.timestamp() * 1000
            if schedule.stagger_ms:
                import random
                result += random.randint(0, schedule.stagger_ms)
            return result
        except ImportError:
            # Fallback: treat as every 5 min
            return now_ms + 300_000

    return now_ms + 60_000


def parse_every(spec: str) -> int:
    """Parse a duration string like '30m', '1h', '2d' to milliseconds."""
    match = re.match(r"^(\d+)\s*(ms|s|m|h|d)$", spec.strip())
    if not match:
        return 0
    value = int(match.group(1))
    unit = match.group(2)
    multipliers = {"ms": 1, "s": 1000, "m": 60_000, "h": 3_600_000, "d": 86_400_000}
    return value * multipliers.get(unit, 0)


def is_due(next_run_ms: float, now_ms: float | None = None) -> bool:
    """Check if a job is due to run."""
    if now_ms is None:
        now_ms = time.time() * 1000
    return next_run_ms <= now_ms
