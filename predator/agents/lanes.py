"""Command lanes — routes agent traffic by type.

Mirrors OpenClaw's lanes.ts: separates main agent, subagent, and nested traffic
so the gateway can prioritize and isolate execution paths.
"""

from __future__ import annotations

from enum import Enum


class CommandLane(str, Enum):
    """Execution lanes for agent commands."""

    MAIN = "main"           # Primary user-facing agent
    SUBAGENT = "subagent"   # Spawned subagent workloads
    NESTED = "nested"       # Nested task execution (inline)
    CRON = "cron"           # Scheduled/cron job execution


def get_lane_label(lane: CommandLane) -> str:
    """Human-readable label for a command lane."""
    labels = {
        CommandLane.MAIN: "Main Agent",
        CommandLane.SUBAGENT: "Subagent",
        CommandLane.NESTED: "Nested Task",
        CommandLane.CRON: "Cron Job",
    }
    return labels.get(lane, lane.value)
