"""Channel action tools — platform-specific actions for Telegram, Discord, and Slack.

Let the agent perform rich interactions beyond simple text messaging:
photos, embeds, threads, reactions, file uploads, channel info, etc.
"""

from __future__ import annotations

from typing import Any, Callable, Optional

from predator.tools.base import BaseTool, ToolCategory, ToolResult
from predator.utils.logger import get_logger

log = get_logger("agents.tools.channel_actions")


def _get_registry():
    """Return a shared ChannelRegistry (lazy import to avoid circular deps)."""
    from predator.channels.registry import create_default_registry

    if not hasattr(_get_registry, "_instance"):
        _get_registry._instance = create_default_registry()  # type: ignore[attr-defined]
    return _get_registry._instance  # type: ignore[attr-defined]


# ---------------------------------------------------------------------------
# Telegram Actions
# ---------------------------------------------------------------------------

_TELEGRAM_ACTIONS = [
    "send_photo",
    "send_document",
    "pin_message",
    "get_chat_info",
    "get_members",
]


class TelegramActionsTool(BaseTool):
    """Perform Telegram-specific actions in a chat.

    Supported actions:
    - send_photo: Send an image file to a chat.
    - send_document: Send a file/document to a chat.
    - pin_message: Pin a message in a chat.
    - get_chat_info: Retrieve metadata about a chat.
    - get_members: List members of a group/supergroup.
    """

    name = "telegram_actions"
    description = (
        "Execute Telegram-specific actions such as sending photos or "
        "documents, pinning messages, and retrieving chat or member info. "
        "Requires the Telegram channel to be configured and connected."
    )
    category = ToolCategory.SESSION

    def get_parameters(self) -> dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "action": {
                    "type": "string",
                    "description": "The Telegram action to perform.",
                    "enum": _TELEGRAM_ACTIONS,
                },
                "chat_id": {
                    "type": "string",
                    "description": (
                        "Target Telegram chat ID (numeric ID or @username)."
                    ),
                },
                "file_path": {
                    "type": "string",
                    "description": (
                        "Local file path for send_photo / send_document actions."
                    ),
                },
                "message_id": {
                    "type": "string",
                    "description": (
                        "Message ID for pin_message action."
                    ),
                },
            },
            "required": ["action", "chat_id"],
        }

    async def execute(
        self,
        tool_call_id: str,
        arguments: dict[str, Any],
        on_update: Optional[Callable[[str], None]] = None,
    ) -> ToolResult:
        action = arguments.get("action", "").strip()
        chat_id = arguments.get("chat_id", "").strip()
        file_path = arguments.get("file_path", "").strip() if arguments.get("file_path") else None
        message_id = arguments.get("message_id", "").strip() if arguments.get("message_id") else None

        if action not in _TELEGRAM_ACTIONS:
            return ToolResult(
                output=(
                    f"Unknown Telegram action: '{action}'. "
                    f"Supported: {', '.join(_TELEGRAM_ACTIONS)}"
                ),
                is_error=True,
            )

        if not chat_id:
            return ToolResult(output="Missing required parameter: chat_id", is_error=True)

        # Validate action-specific params
        if action in ("send_photo", "send_document") and not file_path:
            return ToolResult(
                output=f"Action '{action}' requires the 'file_path' parameter.",
                is_error=True,
            )
        if action == "pin_message" and not message_id:
            return ToolResult(
                output="Action 'pin_message' requires the 'message_id' parameter.",
                is_error=True,
            )

        registry = _get_registry()
        plugin = registry.get("telegram")
        if plugin is None:
            return ToolResult(
                output="Telegram channel is not configured or not available.",
                is_error=True,
            )

        log.info(f"Telegram action: {action} on chat {chat_id}")

        try:
            if action == "send_photo":
                result = await plugin.execute_action(
                    action="send_photo",
                    chat_id=chat_id,
                    file_path=file_path,
                )
            elif action == "send_document":
                result = await plugin.execute_action(
                    action="send_document",
                    chat_id=chat_id,
                    file_path=file_path,
                )
            elif action == "pin_message":
                result = await plugin.execute_action(
                    action="pin_message",
                    chat_id=chat_id,
                    message_id=message_id,
                )
            elif action == "get_chat_info":
                result = await plugin.execute_action(
                    action="get_chat_info",
                    chat_id=chat_id,
                )
            elif action == "get_members":
                result = await plugin.execute_action(
                    action="get_members",
                    chat_id=chat_id,
                )
            else:
                return ToolResult(output=f"Unhandled action: {action}", is_error=True)

            log.info(f"Telegram action '{action}' completed on chat {chat_id}")
            return ToolResult(
                output=f"Telegram action '{action}' completed successfully on chat {chat_id}.",
                metadata={"action": action, "chat_id": chat_id, "result": result},
            )
        except NotImplementedError:
            return ToolResult(
                output=f"Telegram channel does not support action '{action}'.",
                is_error=True,
            )
        except Exception as exc:
            return ToolResult(
                output=f"Telegram action '{action}' failed: {exc}",
                is_error=True,
            )


# ---------------------------------------------------------------------------
# Discord Actions
# ---------------------------------------------------------------------------

_DISCORD_ACTIONS = [
    "send_embed",
    "create_thread",
    "add_reaction",
    "get_channel_info",
    "list_members",
]


class DiscordActionsTool(BaseTool):
    """Perform Discord-specific actions in a channel or guild.

    Supported actions:
    - send_embed: Send a rich embed message to a channel.
    - create_thread: Create a new thread in a channel.
    - add_reaction: Add an emoji reaction to a message.
    - get_channel_info: Retrieve metadata about a channel.
    - list_members: List members of a guild/server.
    """

    name = "discord_actions"
    description = (
        "Execute Discord-specific actions such as sending embeds, creating "
        "threads, adding reactions, and retrieving channel or member info. "
        "Requires the Discord channel to be configured and connected."
    )
    category = ToolCategory.SESSION

    def get_parameters(self) -> dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "action": {
                    "type": "string",
                    "description": "The Discord action to perform.",
                    "enum": _DISCORD_ACTIONS,
                },
                "channel_id": {
                    "type": "string",
                    "description": "Target Discord channel or guild ID.",
                },
                "data": {
                    "type": "object",
                    "description": (
                        "Action-specific data payload. Contents depend on the action:\n"
                        "- send_embed: {title, description, color, fields, footer, image_url}\n"
                        "- create_thread: {name, message_id, auto_archive_duration}\n"
                        "- add_reaction: {message_id, emoji}\n"
                        "- get_channel_info: {} (no extra data needed)\n"
                        "- list_members: {limit, after}"
                    ),
                },
            },
            "required": ["action", "channel_id"],
        }

    async def execute(
        self,
        tool_call_id: str,
        arguments: dict[str, Any],
        on_update: Optional[Callable[[str], None]] = None,
    ) -> ToolResult:
        action = arguments.get("action", "").strip()
        channel_id = arguments.get("channel_id", "").strip()
        data = arguments.get("data") or {}

        if action not in _DISCORD_ACTIONS:
            return ToolResult(
                output=(
                    f"Unknown Discord action: '{action}'. "
                    f"Supported: {', '.join(_DISCORD_ACTIONS)}"
                ),
                is_error=True,
            )

        if not channel_id:
            return ToolResult(output="Missing required parameter: channel_id", is_error=True)

        # Validate action-specific data
        if action == "send_embed" and not data.get("title") and not data.get("description"):
            return ToolResult(
                output="Action 'send_embed' requires at least 'title' or 'description' in data.",
                is_error=True,
            )
        if action == "create_thread" and not data.get("name"):
            return ToolResult(
                output="Action 'create_thread' requires 'name' in data.",
                is_error=True,
            )
        if action == "add_reaction" and (not data.get("message_id") or not data.get("emoji")):
            return ToolResult(
                output="Action 'add_reaction' requires 'message_id' and 'emoji' in data.",
                is_error=True,
            )

        registry = _get_registry()
        plugin = registry.get("discord")
        if plugin is None:
            return ToolResult(
                output="Discord channel is not configured or not available.",
                is_error=True,
            )

        log.info(f"Discord action: {action} on channel {channel_id}")

        try:
            result = await plugin.execute_action(
                action=action,
                channel_id=channel_id,
                data=data,
            )

            log.info(f"Discord action '{action}' completed on channel {channel_id}")
            return ToolResult(
                output=f"Discord action '{action}' completed successfully on channel {channel_id}.",
                metadata={"action": action, "channel_id": channel_id, "result": result},
            )
        except NotImplementedError:
            return ToolResult(
                output=f"Discord channel does not support action '{action}'.",
                is_error=True,
            )
        except Exception as exc:
            return ToolResult(
                output=f"Discord action '{action}' failed: {exc}",
                is_error=True,
            )


# ---------------------------------------------------------------------------
# Slack Actions
# ---------------------------------------------------------------------------

_SLACK_ACTIONS = [
    "send_block",
    "create_channel",
    "upload_file",
    "get_channel_info",
    "list_users",
]


class SlackActionsTool(BaseTool):
    """Perform Slack-specific actions in a workspace.

    Supported actions:
    - send_block: Send a Block Kit message to a channel.
    - create_channel: Create a new Slack channel.
    - upload_file: Upload a file to a channel.
    - get_channel_info: Retrieve metadata about a channel.
    - list_users: List users in the workspace.
    """

    name = "slack_actions"
    description = (
        "Execute Slack-specific actions such as sending Block Kit messages, "
        "creating channels, uploading files, and retrieving channel or user "
        "info. Requires the Slack channel to be configured and connected."
    )
    category = ToolCategory.SESSION

    def get_parameters(self) -> dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "action": {
                    "type": "string",
                    "description": "The Slack action to perform.",
                    "enum": _SLACK_ACTIONS,
                },
                "channel": {
                    "type": "string",
                    "description": (
                        "Target Slack channel ID or name (e.g. '#general' or 'C01234ABCDE')."
                    ),
                },
                "data": {
                    "type": "object",
                    "description": (
                        "Action-specific data payload. Contents depend on the action:\n"
                        "- send_block: {blocks (list), text (fallback), thread_ts}\n"
                        "- create_channel: {name, is_private}\n"
                        "- upload_file: {file_path, filename, title, initial_comment}\n"
                        "- get_channel_info: {} (no extra data needed)\n"
                        "- list_users: {limit, cursor}"
                    ),
                },
            },
            "required": ["action", "channel"],
        }

    async def execute(
        self,
        tool_call_id: str,
        arguments: dict[str, Any],
        on_update: Optional[Callable[[str], None]] = None,
    ) -> ToolResult:
        action = arguments.get("action", "").strip()
        channel = arguments.get("channel", "").strip()
        data = arguments.get("data") or {}

        if action not in _SLACK_ACTIONS:
            return ToolResult(
                output=(
                    f"Unknown Slack action: '{action}'. "
                    f"Supported: {', '.join(_SLACK_ACTIONS)}"
                ),
                is_error=True,
            )

        if not channel:
            return ToolResult(output="Missing required parameter: channel", is_error=True)

        # Validate action-specific data
        if action == "send_block" and not data.get("blocks"):
            return ToolResult(
                output="Action 'send_block' requires 'blocks' (list) in data.",
                is_error=True,
            )
        if action == "create_channel" and not data.get("name"):
            return ToolResult(
                output="Action 'create_channel' requires 'name' in data.",
                is_error=True,
            )
        if action == "upload_file" and not data.get("file_path"):
            return ToolResult(
                output="Action 'upload_file' requires 'file_path' in data.",
                is_error=True,
            )

        registry = _get_registry()
        plugin = registry.get("slack")
        if plugin is None:
            return ToolResult(
                output="Slack channel is not configured or not available.",
                is_error=True,
            )

        log.info(f"Slack action: {action} on channel {channel}")

        try:
            result = await plugin.execute_action(
                action=action,
                channel=channel,
                data=data,
            )

            log.info(f"Slack action '{action}' completed on channel {channel}")
            return ToolResult(
                output=f"Slack action '{action}' completed successfully on channel {channel}.",
                metadata={"action": action, "channel": channel, "result": result},
            )
        except NotImplementedError:
            return ToolResult(
                output=f"Slack channel does not support action '{action}'.",
                is_error=True,
            )
        except Exception as exc:
            return ToolResult(
                output=f"Slack action '{action}' failed: {exc}",
                is_error=True,
            )
