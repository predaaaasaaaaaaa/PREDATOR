"""Cron management tools — lets the agent create and manage scheduled reconnaissance jobs.

Three tools:
- CronCreateTool: Create a new scheduled job.
- CronListTool: List all scheduled jobs with status info.
- CronManageTool: Enable, disable, or delete a cron job.
"""

from __future__ import annotations

import re
import time
from datetime import datetime, timezone
from typing import Any, Callable, Optional

from predator.cron.service import CronService
from predator.cron.types import (
    CronJob,
    CronJobState,
    CronPayload,
    CronSchedule,
    ScheduleKind,
)
from predator.tools.base import BaseTool, ToolCategory, ToolResult
from predator.utils.logger import get_logger

log = get_logger("agents.tools.cron_tool")

# Regex for parsing "every" interval values like "30m", "1h", "2d", "90s"
_INTERVAL_RE = re.compile(r"^(\d+)\s*(s|m|h|d)$", re.IGNORECASE)

_INTERVAL_MULTIPLIERS = {
    "s": 1_000,
    "m": 60_000,
    "h": 3_600_000,
    "d": 86_400_000,
}


def _parse_every_interval(value: str) -> int:
    """Parse an interval string like '30m' or '1h' into milliseconds."""
    match = _INTERVAL_RE.match(value.strip())
    if not match:
        raise ValueError(
            f"Invalid interval format '{value}'. "
            "Expected format like '30s', '5m', '1h', or '2d'."
        )
    amount = int(match.group(1))
    unit = match.group(2).lower()
    return amount * _INTERVAL_MULTIPLIERS[unit]


def _format_timestamp_ms(ts_ms: float) -> str:
    """Format a millisecond timestamp as a human-readable UTC string."""
    if not ts_ms:
        return "never"
    dt = datetime.fromtimestamp(ts_ms / 1000, tz=timezone.utc)
    return dt.strftime("%Y-%m-%d %H:%M:%S UTC")


# ---------------------------------------------------------------------------
# CronCreateTool
# ---------------------------------------------------------------------------


class CronCreateTool(BaseTool):
    """Create a new scheduled reconnaissance job.

    Supports three schedule kinds:
    - "at": one-shot at a specific ISO datetime
    - "every": recurring at a fixed interval (e.g. "30m", "1h")
    - "cron": recurring via a cron expression
    """

    name = "cron_create"
    description = (
        "Create a new scheduled cron job. The job will send a message to the "
        "agent on the specified schedule. Use schedule_kind='at' for one-shot "
        "jobs, 'every' for fixed intervals (e.g. '30m', '1h'), or 'cron' for "
        "cron expressions."
    )
    category = ToolCategory.SESSION

    def __init__(self, _cron_service: Optional[CronService] = None) -> None:
        self._cron_service = _cron_service

    def get_parameters(self) -> dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "name": {
                    "type": "string",
                    "description": "Human-readable name for the cron job.",
                },
                "message": {
                    "type": "string",
                    "description": (
                        "The message/instruction to send to the agent when "
                        "the job fires."
                    ),
                },
                "schedule_kind": {
                    "type": "string",
                    "enum": ["at", "every", "cron"],
                    "description": (
                        "Schedule type: 'at' for a one-shot ISO datetime, "
                        "'every' for a fixed interval (e.g. '30m', '1h'), "
                        "or 'cron' for a cron expression."
                    ),
                },
                "schedule_value": {
                    "type": "string",
                    "description": (
                        "Schedule value. For 'at': an ISO 8601 datetime "
                        "(e.g. '2025-06-01T14:00:00Z'). For 'every': an "
                        "interval string (e.g. '30m', '1h', '2d'). For "
                        "'cron': a cron expression (e.g. '*/5 * * * *')."
                    ),
                },
                "timezone": {
                    "type": "string",
                    "description": (
                        "Timezone for cron expressions (e.g. 'US/Eastern', "
                        "'Europe/London'). Optional, defaults to UTC."
                    ),
                },
                "timeout_seconds": {
                    "type": "number",
                    "description": (
                        "Maximum execution time in seconds for each job run. "
                        "Defaults to 600 (10 minutes)."
                    ),
                },
            },
            "required": ["name", "message", "schedule_kind", "schedule_value"],
        }

    async def execute(
        self,
        tool_call_id: str,
        arguments: dict[str, Any],
        on_update: Optional[Callable[[str], None]] = None,
    ) -> ToolResult:
        if self._cron_service is None:
            return ToolResult(
                output="Cron service is not available.", is_error=True
            )

        name: str = arguments["name"]
        message: str = arguments["message"]
        schedule_kind: str = arguments["schedule_kind"]
        schedule_value: str = arguments["schedule_value"]
        tz: str = arguments.get("timezone", "")
        timeout: int = int(arguments.get("timeout_seconds", 600))

        # Build the schedule
        try:
            kind = ScheduleKind(schedule_kind)
        except ValueError:
            return ToolResult(
                output=f"Invalid schedule_kind '{schedule_kind}'. Must be 'at', 'every', or 'cron'.",
                is_error=True,
            )

        schedule = CronSchedule(kind=kind, tz=tz)

        if kind == ScheduleKind.AT:
            # Validate ISO datetime
            try:
                datetime.fromisoformat(schedule_value.replace("Z", "+00:00"))
            except ValueError:
                return ToolResult(
                    output=f"Invalid ISO datetime: '{schedule_value}'.",
                    is_error=True,
                )
            schedule.at = schedule_value

        elif kind == ScheduleKind.EVERY:
            try:
                every_ms = _parse_every_interval(schedule_value)
            except ValueError as e:
                return ToolResult(output=str(e), is_error=True)
            schedule.every_ms = every_ms

        elif kind == ScheduleKind.CRON:
            schedule.expr = schedule_value

        # Build the job
        job = CronJob(
            name=name,
            enabled=True,
            delete_after_run=(kind == ScheduleKind.AT),
            schedule=schedule,
            payload=CronPayload(
                kind="agent_turn",
                message=message,
                timeout_seconds=timeout,
            ),
        )

        created = self._cron_service.add_job(job)
        log.info(f"Created cron job '{name}' (id={created.id})")

        return ToolResult(
            output=(
                f"Cron job created successfully.\n"
                f"  ID: {created.id}\n"
                f"  Name: {created.name}\n"
                f"  Schedule: {schedule_kind} = {schedule_value}\n"
                f"  Next run: {_format_timestamp_ms(created.state.next_run_at_ms)}"
            ),
            metadata={"job_id": created.id},
        )


# ---------------------------------------------------------------------------
# CronListTool
# ---------------------------------------------------------------------------


class CronListTool(BaseTool):
    """List all scheduled cron jobs with their status information."""

    name = "cron_list"
    description = (
        "List all scheduled cron jobs. Returns each job's ID, name, "
        "enabled status, schedule, last run time, and next run time."
    )
    category = ToolCategory.SESSION

    def __init__(self, _cron_service: Optional[CronService] = None) -> None:
        self._cron_service = _cron_service

    def get_parameters(self) -> dict[str, Any]:
        return {
            "type": "object",
            "properties": {},
            "required": [],
        }

    async def execute(
        self,
        tool_call_id: str,
        arguments: dict[str, Any],
        on_update: Optional[Callable[[str], None]] = None,
    ) -> ToolResult:
        if self._cron_service is None:
            return ToolResult(
                output="Cron service is not available.", is_error=True
            )

        jobs = self._cron_service.list_jobs()
        if not jobs:
            return ToolResult(output="No cron jobs found.")

        lines: list[str] = [f"Found {len(jobs)} cron job(s):\n"]
        for job in jobs:
            status = "enabled" if job.enabled else "disabled"
            schedule_desc = _describe_schedule(job.schedule)
            last_run = _format_timestamp_ms(job.state.last_run_at_ms)
            next_run = _format_timestamp_ms(job.state.next_run_at_ms)
            last_status = job.state.last_status or "n/a"

            lines.append(
                f"- [{job.id}] {job.name}\n"
                f"    Status: {status} | Last result: {last_status}\n"
                f"    Schedule: {schedule_desc}\n"
                f"    Last run: {last_run}\n"
                f"    Next run: {next_run}"
            )

        return ToolResult(
            output="\n".join(lines),
            metadata={"job_count": len(jobs)},
        )


def _describe_schedule(sched: CronSchedule) -> str:
    """Return a human-readable description of a schedule."""
    if sched.kind == ScheduleKind.AT:
        return f"one-shot at {sched.at}"
    elif sched.kind == ScheduleKind.EVERY:
        # Convert ms back to a readable form
        total_s = sched.every_ms // 1000
        if total_s >= 86400 and total_s % 86400 == 0:
            return f"every {total_s // 86400}d"
        if total_s >= 3600 and total_s % 3600 == 0:
            return f"every {total_s // 3600}h"
        if total_s >= 60 and total_s % 60 == 0:
            return f"every {total_s // 60}m"
        return f"every {total_s}s"
    elif sched.kind == ScheduleKind.CRON:
        tz_str = f" ({sched.tz})" if sched.tz else ""
        return f"cron: {sched.expr}{tz_str}"
    return "unknown"


# ---------------------------------------------------------------------------
# CronManageTool
# ---------------------------------------------------------------------------


class CronManageTool(BaseTool):
    """Enable, disable, or delete a cron job by ID."""

    name = "cron_manage"
    description = (
        "Manage an existing cron job. Actions: 'enable' to resume a paused "
        "job, 'disable' to pause it without deleting, or 'delete' to remove "
        "it permanently."
    )
    category = ToolCategory.SESSION

    def __init__(self, _cron_service: Optional[CronService] = None) -> None:
        self._cron_service = _cron_service

    def get_parameters(self) -> dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "job_id": {
                    "type": "string",
                    "description": "The ID of the cron job to manage.",
                },
                "action": {
                    "type": "string",
                    "enum": ["enable", "disable", "delete"],
                    "description": (
                        "Action to perform: 'enable', 'disable', or 'delete'."
                    ),
                },
            },
            "required": ["job_id", "action"],
        }

    async def execute(
        self,
        tool_call_id: str,
        arguments: dict[str, Any],
        on_update: Optional[Callable[[str], None]] = None,
    ) -> ToolResult:
        if self._cron_service is None:
            return ToolResult(
                output="Cron service is not available.", is_error=True
            )

        job_id: str = arguments["job_id"]
        action: str = arguments["action"]

        if action not in ("enable", "disable", "delete"):
            return ToolResult(
                output=f"Invalid action '{action}'. Must be 'enable', 'disable', or 'delete'.",
                is_error=True,
            )

        if action == "enable":
            ok = self._cron_service.enable_job(job_id)
            if ok:
                return ToolResult(output=f"Cron job '{job_id}' has been enabled.")
            return ToolResult(
                output=f"Cron job '{job_id}' not found.", is_error=True
            )

        if action == "disable":
            ok = self._cron_service.disable_job(job_id)
            if ok:
                return ToolResult(output=f"Cron job '{job_id}' has been disabled.")
            return ToolResult(
                output=f"Cron job '{job_id}' not found.", is_error=True
            )

        # action == "delete"
        ok = self._cron_service.remove_job(job_id)
        if ok:
            return ToolResult(output=f"Cron job '{job_id}' has been deleted.")
        return ToolResult(
            output=f"Cron job '{job_id}' not found.", is_error=True
        )
