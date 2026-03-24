"""Hook type definitions — mirrors OpenClaw's hooks/types.ts and internal-hooks.ts."""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from typing import Any, Callable, Awaitable, Optional


class HookEvent(str, Enum):
    """Hook events that plugins and config can subscribe to."""

    # Agent lifecycle
    AGENT_START = "agent_start"
    AGENT_END = "agent_end"

    # Tool execution
    BEFORE_TOOL_CALL = "before_tool_call"
    AFTER_TOOL_CALL = "after_tool_call"

    # Message flow
    MESSAGE_RECEIVED = "message_received"
    MESSAGE_SENDING = "message_sending"
    MESSAGE_SENT = "message_sent"

    # Session lifecycle
    SESSION_START = "session_start"
    SESSION_END = "session_end"

    # LLM interaction
    BEFORE_MODEL_RESOLVE = "before_model_resolve"
    BEFORE_PROMPT_BUILD = "before_prompt_build"
    LLM_INPUT = "llm_input"
    LLM_OUTPUT = "llm_output"

    # Gateway lifecycle
    GATEWAY_START = "gateway_start"
    GATEWAY_STOP = "gateway_stop"

    # Compaction
    BEFORE_COMPACTION = "before_compaction"
    AFTER_COMPACTION = "after_compaction"


# Hook handler type
HookHandler = Callable[[dict[str, Any]], Awaitable[Optional[dict[str, Any]]]]


@dataclass
class HookRegistration:
    """A registered hook handler."""

    event: HookEvent
    handler: HookHandler
    source: str = "config"  # config | plugin | builtin
    priority: int = 100  # Lower = runs first
    name: str = ""
