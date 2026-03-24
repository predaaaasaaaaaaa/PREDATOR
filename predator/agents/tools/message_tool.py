"""Message tools — let the agent send messages through configured channels.

Two tools:
- SendMessageTool: Send a message to a specific channel/user.
- SendAlertTool: Send a structured priority alert.
"""

from __future__ import annotations

from datetime import datetime
from typing import Any, Callable, Optional

from predator.tools.base import BaseTool, ToolCategory, ToolResult
from predator.utils.logger import get_logger

log = get_logger("agents.tools.message")

_SUPPORTED_CHANNELS = ["telegram", "discord", "slack", "irc", "whatsapp"]


def _get_registry():
    """Return a shared ChannelRegistry (lazy import to avoid circular deps)."""
    from predator.channels.registry import create_default_registry

    if not hasattr(_get_registry, "_instance"):
        _get_registry._instance = create_default_registry()  # type: ignore[attr-defined]
    return _get_registry._instance  # type: ignore[attr-defined]


# ---------------------------------------------------------------------------
# SendMessageTool
# ---------------------------------------------------------------------------

class SendMessageTool(BaseTool):
    """Send a text message to a specific channel and recipient.

    Supports Telegram, Discord, Slack, IRC, and WhatsApp channels.  The
    message is delivered via the channel plugin registered in the
    ChannelRegistry.
    """

    name = "send_message"
    description = (
        "Send a text message to a user or chat via a configured channel "
        "(telegram, discord, slack, irc, whatsapp). Use this to notify "
        "operators, deliver results, or communicate through chat platforms."
    )
    category = ToolCategory.SESSION

    def get_parameters(self) -> dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "channel": {
                    "type": "string",
                    "description": "Channel to send through.",
                    "enum": _SUPPORTED_CHANNELS,
                },
                "to": {
                    "type": "string",
                    "description": (
                        "Recipient identifier — a chat ID, username, channel name, "
                        "or phone number depending on the channel."
                    ),
                },
                "text": {
                    "type": "string",
                    "description": "The message text to send.",
                },
                "account_id": {
                    "type": "string",
                    "description": (
                        "Account/bot ID to send from (default: 'default'). "
                        "Only needed when multiple accounts are configured for a channel."
                    ),
                },
            },
            "required": ["channel", "to", "text"],
        }

    async def execute(
        self,
        tool_call_id: str,
        arguments: dict[str, Any],
        on_update: Optional[Callable[[str], None]] = None,
    ) -> ToolResult:
        channel_id = arguments.get("channel", "").strip().lower()
        to = arguments.get("to", "").strip()
        text = arguments.get("text", "").strip()
        account_id = arguments.get("account_id", "default").strip()

        if not channel_id:
            return ToolResult(output="Missing required parameter: channel", is_error=True)
        if not to:
            return ToolResult(output="Missing required parameter: to", is_error=True)
        if not text:
            return ToolResult(output="Missing required parameter: text", is_error=True)

        if channel_id not in _SUPPORTED_CHANNELS:
            return ToolResult(
                output=(
                    f"Unsupported channel: '{channel_id}'. "
                    f"Supported: {', '.join(_SUPPORTED_CHANNELS)}"
                ),
                is_error=True,
            )

        registry = _get_registry()
        plugin = registry.get(channel_id)

        if plugin is None:
            return ToolResult(
                output=(
                    f"Channel '{channel_id}' is not available. "
                    f"Registered channels: {', '.join(registry.list_ids()) or 'none'}"
                ),
                is_error=True,
            )

        log.info(f"Sending message via {channel_id} to {to} ({len(text)} chars)")

        try:
            result = await plugin.send_text(
                to=to,
                text=text,
                account_id=account_id,
            )
            log.info(f"Message sent via {channel_id}: message_id={result.message_id}")
            return ToolResult(
                output=(
                    f"Message sent via {channel_id} to '{to}' "
                    f"(message_id: {result.message_id or 'n/a'})"
                ),
                metadata={
                    "channel": channel_id,
                    "to": to,
                    "message_id": result.message_id,
                    "chat_id": result.chat_id,
                },
            )
        except NotImplementedError:
            return ToolResult(
                output=f"Channel '{channel_id}' does not support sending text messages.",
                is_error=True,
            )
        except Exception as exc:
            return ToolResult(
                output=f"Failed to send message via {channel_id}: {exc}",
                is_error=True,
            )


# ---------------------------------------------------------------------------
# SendAlertTool
# ---------------------------------------------------------------------------

_SEVERITY_PREFIXES = {
    "info": "[INFO]",
    "warning": "[WARNING]",
    "critical": "[CRITICAL]",
}


class SendAlertTool(BaseTool):
    """Send a structured priority alert through a configured channel.

    Alerts are formatted with severity, title, and body — useful for
    notifying operators about scan completions, vulnerability discoveries,
    or other significant events.
    """

    name = "send_alert"
    description = (
        "Send a structured priority alert (e.g., vulnerability found, scan "
        "complete). Formats a clear alert message with severity level and "
        "sends it to the configured alert channel."
    )
    category = ToolCategory.SESSION

    def __init__(self, default_alert_channel: str = "telegram",
                 default_alert_to: str = "") -> None:
        """
        Args:
            default_alert_channel: Channel to use when none is specified.
            default_alert_to: Default recipient for alerts.
        """
        self._default_channel = default_alert_channel
        self._default_to = default_alert_to

    def get_parameters(self) -> dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "title": {
                    "type": "string",
                    "description": "Short alert title (e.g. 'SQL Injection Found', 'Scan Complete').",
                },
                "body": {
                    "type": "string",
                    "description": "Detailed alert body with findings or context.",
                },
                "severity": {
                    "type": "string",
                    "description": "Alert severity level.",
                    "enum": ["info", "warning", "critical"],
                },
                "channel": {
                    "type": "string",
                    "description": (
                        "Channel to send the alert through. If omitted, uses the "
                        "configured default alert channel."
                    ),
                    "enum": _SUPPORTED_CHANNELS,
                },
                "to": {
                    "type": "string",
                    "description": (
                        "Recipient for the alert. If omitted, uses the configured "
                        "default alert recipient."
                    ),
                },
            },
            "required": ["title", "body"],
        }

    async def execute(
        self,
        tool_call_id: str,
        arguments: dict[str, Any],
        on_update: Optional[Callable[[str], None]] = None,
    ) -> ToolResult:
        title = arguments.get("title", "").strip()
        body = arguments.get("body", "").strip()
        severity = arguments.get("severity", "info").strip().lower()
        channel_id = arguments.get("channel", self._default_channel).strip().lower()
        to = arguments.get("to", self._default_to).strip()

        if not title:
            return ToolResult(output="Missing required parameter: title", is_error=True)
        if not body:
            return ToolResult(output="Missing required parameter: body", is_error=True)
        if not to:
            return ToolResult(
                output=(
                    "No alert recipient configured. Provide 'to' parameter or "
                    "configure a default alert recipient."
                ),
                is_error=True,
            )

        if severity not in _SEVERITY_PREFIXES:
            severity = "info"

        # Format the alert message
        prefix = _SEVERITY_PREFIXES[severity]
        timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        separator = "=" * 30

        alert_text = (
            f"{prefix} PREDATOR ALERT\n"
            f"{separator}\n"
            f"Title: {title}\n"
            f"Severity: {severity.upper()}\n"
            f"Time: {timestamp}\n"
            f"{separator}\n\n"
            f"{body}"
        )

        registry = _get_registry()
        plugin = registry.get(channel_id)

        if plugin is None:
            return ToolResult(
                output=(
                    f"Alert channel '{channel_id}' is not available. "
                    f"Registered channels: {', '.join(registry.list_ids()) or 'none'}"
                ),
                is_error=True,
            )

        log.info(f"Sending {severity} alert via {channel_id}: {title}")

        try:
            result = await plugin.send_text(
                to=to,
                text=alert_text,
                account_id="default",
            )
            log.info(f"Alert sent via {channel_id}: message_id={result.message_id}")
            return ToolResult(
                output=(
                    f"Alert sent via {channel_id} to '{to}': "
                    f"{prefix} {title}"
                ),
                metadata={
                    "channel": channel_id,
                    "to": to,
                    "severity": severity,
                    "title": title,
                    "message_id": result.message_id,
                },
            )
        except NotImplementedError:
            return ToolResult(
                output=f"Channel '{channel_id}' does not support sending text messages.",
                is_error=True,
            )
        except Exception as exc:
            return ToolResult(
                output=f"Failed to send alert via {channel_id}: {exc}",
                is_error=True,
            )
