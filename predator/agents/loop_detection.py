"""Tool loop detection — mirrors OpenClaw's tool-loop-detection.ts.

Detects when the agent is stuck in an infinite loop of tool calls
(e.g., repeatedly calling the same command with the same arguments).
"""

from __future__ import annotations

import hashlib
import time
from collections import deque
from dataclasses import dataclass
from typing import Optional


@dataclass
class ToolCallRecord:
    """Record of a tool call for loop detection."""

    tool_name: str
    arguments_hash: str
    timestamp: float
    result_hash: str = ""


class LoopDetector:
    """Detects infinite tool call loops.

    Mirrors OpenClaw's tool loop detection:
    - Tracks recent tool calls with argument hashes
    - Detects repeated identical calls
    - Detects oscillating patterns (A→B→A→B)
    - Configurable thresholds
    """

    def __init__(
        self,
        max_identical_calls: int = 3,
        window_size: int = 20,
        pattern_length: int = 4,
    ) -> None:
        self._history: deque[ToolCallRecord] = deque(maxlen=window_size)
        self._max_identical = max_identical_calls
        self._pattern_length = pattern_length

    def _hash_args(self, arguments: dict) -> str:
        """Create a hash of tool arguments for comparison."""
        import json

        serialized = json.dumps(arguments, sort_keys=True, default=str)
        return hashlib.md5(serialized.encode()).hexdigest()[:12]

    def record_call(
        self,
        tool_name: str,
        arguments: dict,
        result: str = "",
    ) -> None:
        """Record a tool call."""
        self._history.append(
            ToolCallRecord(
                tool_name=tool_name,
                arguments_hash=self._hash_args(arguments),
                timestamp=time.time(),
                result_hash=hashlib.md5(result.encode()).hexdigest()[:12] if result else "",
            )
        )

    def check_loop(self) -> Optional[str]:
        """Check if a loop pattern is detected.

        Returns a description of the detected loop, or None if no loop.
        """
        if len(self._history) < self._max_identical:
            return None

        # Check for identical consecutive calls
        recent = list(self._history)
        last = recent[-1]
        identical_count = 0
        for record in reversed(recent):
            if (
                record.tool_name == last.tool_name
                and record.arguments_hash == last.arguments_hash
            ):
                identical_count += 1
            else:
                break

        if identical_count >= self._max_identical:
            return (
                f"Detected {identical_count} identical calls to '{last.tool_name}' "
                f"with the same arguments. Breaking loop."
            )

        # Check for oscillating patterns (A→B→A→B)
        if len(recent) >= self._pattern_length * 2:
            pattern = [
                (r.tool_name, r.arguments_hash)
                for r in recent[-self._pattern_length:]
            ]
            prev_pattern = [
                (r.tool_name, r.arguments_hash)
                for r in recent[-self._pattern_length * 2 : -self._pattern_length]
            ]
            if pattern == prev_pattern:
                tools = [p[0] for p in pattern]
                return (
                    f"Detected repeating pattern: {' → '.join(tools)}. "
                    f"Breaking loop."
                )

        return None

    def reset(self) -> None:
        """Reset the loop detector."""
        self._history.clear()
