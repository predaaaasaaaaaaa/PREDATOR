"""Audit logger hook — writes JSON-lines audit trail for every tool call.

Event: ``tool:after`` (runs after tool execution completes).

Each line written to ``~/.predator/audit.jsonl`` contains:

* ``timestamp`` — ISO-8601 UTC timestamp
* ``tool`` — name of the tool that was invoked
* ``args_summary`` — truncated string representation of arguments
* ``status`` — ``"ok"`` or ``"error"``
* ``error`` — error message (only present when status is ``"error"``)
"""

from __future__ import annotations

import json
import os
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Optional

from predator.utils.logger import get_logger

log = get_logger("hooks.bundled.audit_logger")

# Maximum length for the serialised args summary
_MAX_ARGS_LEN = 512

# Default audit log location
_DEFAULT_AUDIT_PATH = Path.home() / ".predator" / "audit.jsonl"


class AuditLoggerHook:
    """Logs every completed tool call to an append-only JSONL audit file.

    Parameters
    ----------
    audit_path:
        Override the default ``~/.predator/audit.jsonl`` location.
    """

    EVENT = "tool:after"
    PRIORITY = 90
    NAME = "builtin:audit-logger"

    def __init__(self, audit_path: Optional[str | Path] = None) -> None:
        self.audit_path = Path(audit_path) if audit_path else _DEFAULT_AUDIT_PATH

    async def __call__(self, data: dict[str, Any]) -> Optional[dict[str, Any]]:
        """Append an audit record and pass *data* through unchanged."""
        tool_name = data.get("tool", data.get("tool_name", "unknown"))
        args = data.get("args", data.get("arguments", {}))
        result_status = "error" if data.get("error") else "ok"

        # Build a truncated summary of the arguments
        try:
            args_summary = json.dumps(args, default=str)
        except (TypeError, ValueError):
            args_summary = str(args)
        if len(args_summary) > _MAX_ARGS_LEN:
            args_summary = args_summary[:_MAX_ARGS_LEN] + "..."

        record: dict[str, Any] = {
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "tool": tool_name,
            "args_summary": args_summary,
            "status": result_status,
        }
        if result_status == "error":
            record["error"] = str(data.get("error", ""))

        try:
            os.makedirs(self.audit_path.parent, exist_ok=True)
            with open(self.audit_path, "a", encoding="utf-8") as fh:
                fh.write(json.dumps(record) + "\n")
        except OSError as exc:
            log.warning("Failed to write audit log: %s", exc)

        # Pass-through — audit logger never modifies data
        return data
