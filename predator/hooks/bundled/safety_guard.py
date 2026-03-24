"""Safety guard hook — blocks known-dangerous shell patterns.

Event: ``tool:before`` (runs before tool execution).

When a dangerous pattern is detected the hook sets ``blocked=True`` on
the returned data dict and includes a human-readable ``block_reason``.
"""

from __future__ import annotations

import re
from typing import Any, Optional

from predator.utils.logger import get_logger

log = get_logger("hooks.bundled.safety_guard")

# Each entry is (compiled regex, human-readable description).
_DANGEROUS_PATTERNS: list[tuple[re.Pattern[str], str]] = [
    (
        re.compile(r"\brm\s+-[^\s]*r[^\s]*f[^\s]*\s+/\s*$|\brm\s+-[^\s]*f[^\s]*r[^\s]*\s+/\s*$|\brm\s+-rf\s+/\b"),
        "Recursive forced deletion of root filesystem (rm -rf /)",
    ),
    (
        re.compile(r"\bdd\s+if="),
        "Raw disk write via dd",
    ),
    (
        re.compile(r"\bmkfs\b"),
        "Filesystem formatting via mkfs",
    ),
    (
        re.compile(r":\(\)\s*\{\s*:\s*\|\s*:\s*&\s*\}\s*;\s*:"),
        "Fork bomb",
    ),
]


def _check_args_for_danger(args: Any) -> Optional[str]:
    """Return the reason string if *args* contains a dangerous pattern, else ``None``."""
    # Flatten args into a single string for scanning
    if isinstance(args, dict):
        text = " ".join(str(v) for v in args.values())
    elif isinstance(args, (list, tuple)):
        text = " ".join(str(v) for v in args)
    else:
        text = str(args)

    for pattern, reason in _DANGEROUS_PATTERNS:
        if pattern.search(text):
            return reason
    return None


class SafetyGuardHook:
    """Blocks tool invocations that match known-dangerous shell patterns.

    When a match is found the hook returns the data dict with two extra keys:

    * ``blocked`` — ``True``
    * ``block_reason`` — human-readable explanation
    """

    EVENT = "tool:before"
    PRIORITY = 10  # Very high priority — should run early
    NAME = "builtin:safety-guard"

    async def __call__(self, data: dict[str, Any]) -> Optional[dict[str, Any]]:
        args = data.get("args", data.get("arguments", data.get("command", "")))
        reason = _check_args_for_danger(args)
        if reason:
            log.warning(
                "SafetyGuard BLOCKED tool=%s reason=%s",
                data.get("tool", data.get("tool_name", "unknown")),
                reason,
            )
            data["blocked"] = True
            data["block_reason"] = reason
        return data
