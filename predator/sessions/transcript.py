"""Session transcript — mirrors OpenClaw's JSONL transcript system.

Each session is stored as a JSONL file (one event per line) for
append-only, crash-safe persistence.
"""

from __future__ import annotations

import json
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Optional

from predator.config.paths import get_sessions_dir
from predator.utils.logger import get_logger

log = get_logger("sessions.transcript")


@dataclass
class TranscriptEvent:
    """A single event in the session transcript."""

    type: str  # user_message, assistant_message, tool_call, tool_result, agent_end, etc.
    data: dict[str, Any]
    timestamp: float = field(default_factory=time.time)

    def to_jsonl(self) -> str:
        return json.dumps({
            "type": self.type,
            "data": self.data,
            "timestamp": self.timestamp,
        }, default=str)


class SessionTranscript:
    """JSONL-based session transcript.

    Mirrors OpenClaw's session storage:
    - Append-only JSONL file per session
    - Crash-safe (each line is a complete event)
    - Supports replay and history loading
    """

    def __init__(
        self,
        session_id: str,
        agent_id: str = "default",
        base_dir: Optional[Path] = None,
    ) -> None:
        self.session_id = session_id
        self.agent_id = agent_id
        self._dir = base_dir or get_sessions_dir(agent_id)
        self._file = self._dir / f"{session_id}.jsonl"
        self._events: list[TranscriptEvent] = []
        self._dirty = False

    def add_event(self, event_type: str, data: dict[str, Any]) -> None:
        """Add an event to the transcript."""
        event = TranscriptEvent(type=event_type, data=data)
        self._events.append(event)
        self._dirty = True

        # Append immediately for crash safety
        try:
            with open(self._file, "a", encoding="utf-8") as f:
                f.write(event.to_jsonl() + "\n")
        except OSError as e:
            log.error(f"Failed to write transcript event: {e}")

    def save(self) -> None:
        """Force save (no-op since we append immediately, but mark clean)."""
        self._dirty = False

    def load(self) -> list[TranscriptEvent]:
        """Load all events from the transcript file."""
        events: list[TranscriptEvent] = []
        if not self._file.exists():
            return events

        try:
            with open(self._file, "r", encoding="utf-8") as f:
                for line in f:
                    line = line.strip()
                    if not line:
                        continue
                    try:
                        data = json.loads(line)
                        events.append(TranscriptEvent(
                            type=data["type"],
                            data=data["data"],
                            timestamp=data.get("timestamp", 0),
                        ))
                    except (json.JSONDecodeError, KeyError):
                        continue
        except OSError as e:
            log.error(f"Failed to load transcript: {e}")

        self._events = events
        return events

    def get_message_history(self) -> list[dict[str, str]]:
        """Extract conversation history from transcript for LLM context.

        Returns messages in the format expected by the agent runtime.
        """
        from predator.providers.base import ModelMessage

        messages: list[ModelMessage] = []
        events = self._events or self.load()

        for event in events:
            if event.type == "user_message":
                messages.append(ModelMessage(
                    role="user",
                    content=event.data.get("content", ""),
                ))
            elif event.type == "assistant_message":
                messages.append(ModelMessage(
                    role="assistant",
                    content=event.data.get("content", ""),
                ))

        return messages

    def clear(self) -> None:
        """Clear the transcript."""
        self._events.clear()
        try:
            if self._file.exists():
                self._file.unlink()
        except OSError:
            pass

    @property
    def event_count(self) -> int:
        return len(self._events)

    @property
    def exists(self) -> bool:
        return self._file.exists()


class SessionManager:
    """Manages multiple sessions — mirrors OpenClaw's session management.

    Handles session creation, listing, loading, and cleanup.
    """

    def __init__(self, agent_id: str = "default") -> None:
        self._agent_id = agent_id
        self._active: dict[str, SessionTranscript] = {}

    def get_or_create(self, session_id: str) -> SessionTranscript:
        """Get an existing session or create a new one."""
        if session_id not in self._active:
            transcript = SessionTranscript(session_id, self._agent_id)
            if transcript.exists:
                transcript.load()
            self._active[session_id] = transcript
        return self._active[session_id]

    def list_sessions(self) -> list[str]:
        """List all session IDs."""
        sessions_dir = get_sessions_dir(self._agent_id)
        return [
            p.stem for p in sessions_dir.glob("*.jsonl")
        ]

    def delete_session(self, session_id: str) -> bool:
        """Delete a session."""
        if session_id in self._active:
            self._active[session_id].clear()
            del self._active[session_id]
            return True

        transcript = SessionTranscript(session_id, self._agent_id)
        if transcript.exists:
            transcript.clear()
            return True
        return False
