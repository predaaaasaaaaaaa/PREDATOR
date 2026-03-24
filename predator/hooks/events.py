"""Hook event definitions — canonical list of all lifecycle events.

This module extends the base ``HookEvent`` enum in ``hooks/types.py`` with a
comprehensive registry that covers every hookable point in the PREDATOR
lifecycle.  Use these constants when registering or emitting events to avoid
typos and enable auto-complete.
"""

from __future__ import annotations

from enum import Enum


class PredatorEvent(str, Enum):
    """All hookable lifecycle events in PREDATOR.

    Naming convention: ``<subsystem>_<action>``.
    """

    # ── Gateway lifecycle ────────────────────────────────────────────
    GATEWAY_START = "gateway_start"
    GATEWAY_STOP = "gateway_stop"

    # ── Agent turn lifecycle ─────────────────────────────────────────
    AGENT_TURN_START = "agent_turn_start"
    AGENT_TURN_END = "agent_turn_end"

    # ── Tool execution ───────────────────────────────────────────────
    TOOL_EXECUTE_BEFORE = "tool_execute_before"
    TOOL_EXECUTE_AFTER = "tool_execute_after"

    # ── Channel / messaging ──────────────────────────────────────────
    CHANNEL_MESSAGE_INBOUND = "channel_message_inbound"
    CHANNEL_MESSAGE_OUTBOUND = "channel_message_outbound"

    # ── Cron / scheduled jobs ────────────────────────────────────────
    CRON_JOB_START = "cron_job_start"
    CRON_JOB_END = "cron_job_end"

    # ── Session management ───────────────────────────────────────────
    SESSION_CREATE = "session_create"
    SESSION_DELETE = "session_delete"

    # ── Provider / model switching ───────────────────────────────────
    PROVIDER_SWITCH = "provider_switch"


# Convenience sets for programmatic checks
GATEWAY_EVENTS = frozenset({PredatorEvent.GATEWAY_START, PredatorEvent.GATEWAY_STOP})
AGENT_EVENTS = frozenset({PredatorEvent.AGENT_TURN_START, PredatorEvent.AGENT_TURN_END})
TOOL_EVENTS = frozenset({PredatorEvent.TOOL_EXECUTE_BEFORE, PredatorEvent.TOOL_EXECUTE_AFTER})
CHANNEL_EVENTS = frozenset({PredatorEvent.CHANNEL_MESSAGE_INBOUND, PredatorEvent.CHANNEL_MESSAGE_OUTBOUND})
CRON_EVENTS = frozenset({PredatorEvent.CRON_JOB_START, PredatorEvent.CRON_JOB_END})
SESSION_EVENTS = frozenset({PredatorEvent.SESSION_CREATE, PredatorEvent.SESSION_DELETE})

ALL_EVENTS = frozenset(PredatorEvent)
