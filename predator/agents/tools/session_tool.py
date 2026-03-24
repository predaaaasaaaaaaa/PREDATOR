"""Session management tools — lets the agent manage conversation sessions.

Three tools:
- SessionListTool: List active sessions.
- SessionHistoryTool: Get conversation history for a session.
- SessionDeleteTool: Delete/clear a session.
"""

from __future__ import annotations

import time
from datetime import datetime, timezone
from typing import Any, Callable, Optional

from predator.sessions.transcript import SessionManager, SessionTranscript
from predator.tools.base import BaseTool, ToolCategory, ToolResult
from predator.utils.logger import get_logger

log = get_logger("agents.tools.session_tool")


def _format_timestamp(ts: float) -> str:
    """Format a Unix timestamp as a human-readable UTC string."""
    if not ts:
        return "unknown"
    dt = datetime.fromtimestamp(ts, tz=timezone.utc)
    return dt.strftime("%Y-%m-%d %H:%M:%S UTC")


# ---------------------------------------------------------------------------
# SessionListTool
# ---------------------------------------------------------------------------


class SessionListTool(BaseTool):
    """List all active/stored sessions with basic metadata."""

    name = "session_list"
    description = (
        "List all conversation sessions. Returns session IDs, message counts, "
        "and timestamps for each session."
    )
    category = ToolCategory.SESSION

    def __init__(self, _session_manager: Optional[SessionManager] = None) -> None:
        self._session_manager = _session_manager

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
        if self._session_manager is None:
            return ToolResult(
                output="Session manager is not available.", is_error=True
            )

        session_ids = self._session_manager.list_sessions()
        if not session_ids:
            return ToolResult(output="No sessions found.")

        lines: list[str] = [f"Found {len(session_ids)} session(s):\n"]
        for sid in session_ids:
            transcript = self._session_manager.get_or_create(sid)
            events = transcript.load() if not transcript.event_count else transcript._events
            event_count = len(events)

            # Derive timestamps from first and last events
            first_ts = _format_timestamp(events[0].timestamp) if events else "unknown"
            last_ts = _format_timestamp(events[-1].timestamp) if events else "unknown"

            # Count messages (user + assistant only)
            msg_count = sum(
                1
                for e in events
                if e.type in ("user_message", "assistant_message")
            )

            lines.append(
                f"- [{sid}]\n"
                f"    Messages: {msg_count} | Events: {event_count}\n"
                f"    Created: {first_ts}\n"
                f"    Last activity: {last_ts}"
            )

        return ToolResult(
            output="\n".join(lines),
            metadata={"session_count": len(session_ids)},
        )


# ---------------------------------------------------------------------------
# SessionHistoryTool
# ---------------------------------------------------------------------------


class SessionHistoryTool(BaseTool):
    """Get conversation history for a specific session."""

    name = "session_history"
    description = (
        "Retrieve recent conversation history for a session. Returns the "
        "last N messages (user and assistant) from the session transcript."
    )
    category = ToolCategory.SESSION

    def __init__(self, _session_manager: Optional[SessionManager] = None) -> None:
        self._session_manager = _session_manager

    def get_parameters(self) -> dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "session_id": {
                    "type": "string",
                    "description": "The ID of the session to retrieve history from.",
                },
                "limit": {
                    "type": "number",
                    "description": (
                        "Maximum number of messages to return. Defaults to 20."
                    ),
                },
            },
            "required": ["session_id"],
        }

    async def execute(
        self,
        tool_call_id: str,
        arguments: dict[str, Any],
        on_update: Optional[Callable[[str], None]] = None,
    ) -> ToolResult:
        if self._session_manager is None:
            return ToolResult(
                output="Session manager is not available.", is_error=True
            )

        session_id: str = arguments["session_id"]
        limit: int = int(arguments.get("limit", 20))

        # Check if the session exists
        existing_ids = self._session_manager.list_sessions()
        if session_id not in existing_ids:
            return ToolResult(
                output=f"Session '{session_id}' not found.",
                is_error=True,
            )

        transcript = self._session_manager.get_or_create(session_id)
        events = transcript.load() if not transcript.event_count else transcript._events

        # Filter to user/assistant messages only
        messages = [
            e for e in events
            if e.type in ("user_message", "assistant_message")
        ]

        # Take the last `limit` messages
        recent = messages[-limit:]

        if not recent:
            return ToolResult(
                output=f"Session '{session_id}' has no messages."
            )

        lines: list[str] = [
            f"Session '{session_id}' — showing {len(recent)} of {len(messages)} message(s):\n"
        ]
        for event in recent:
            role = "User" if event.type == "user_message" else "Assistant"
            ts = _format_timestamp(event.timestamp)
            content = event.data.get("content", "")
            # Truncate very long messages for readability
            if len(content) > 500:
                content = content[:500] + "... (truncated)"
            lines.append(f"[{ts}] {role}:\n{content}\n")

        return ToolResult(
            output="\n".join(lines),
            metadata={
                "session_id": session_id,
                "total_messages": len(messages),
                "returned": len(recent),
            },
        )


# ---------------------------------------------------------------------------
# SessionDeleteTool
# ---------------------------------------------------------------------------


class SessionDeleteTool(BaseTool):
    """Delete/clear a conversation session."""

    name = "session_delete"
    description = (
        "Delete a conversation session and its transcript. This permanently "
        "removes all messages and events for the given session."
    )
    category = ToolCategory.SESSION

    def __init__(self, _session_manager: Optional[SessionManager] = None) -> None:
        self._session_manager = _session_manager

    def get_parameters(self) -> dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "session_id": {
                    "type": "string",
                    "description": "The ID of the session to delete.",
                },
            },
            "required": ["session_id"],
        }

    async def execute(
        self,
        tool_call_id: str,
        arguments: dict[str, Any],
        on_update: Optional[Callable[[str], None]] = None,
    ) -> ToolResult:
        if self._session_manager is None:
            return ToolResult(
                output="Session manager is not available.", is_error=True
            )

        session_id: str = arguments["session_id"]

        deleted = self._session_manager.delete_session(session_id)
        if deleted:
            log.info(f"Deleted session '{session_id}'")
            return ToolResult(
                output=f"Session '{session_id}' has been deleted.",
                metadata={"session_id": session_id},
            )

        return ToolResult(
            output=f"Session '{session_id}' not found.",
            is_error=True,
        )
