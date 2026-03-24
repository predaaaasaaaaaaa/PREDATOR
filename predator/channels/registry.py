"""Channel registry — manages all available channel plugins."""
from __future__ import annotations
import logging
from typing import Any
from predator.channels.types import ChannelPlugin, ChannelMeta

logger = logging.getLogger(__name__)

CHANNEL_ORDER = ["telegram", "discord", "whatsapp", "slack", "irc", "signal", "matrix"]

class ChannelRegistry:
    def __init__(self):
        self._channels: dict[str, ChannelPlugin] = {}

    def register(self, plugin: ChannelPlugin) -> None:
        self._channels[plugin.id] = plugin
        logger.debug(f"Registered channel: {plugin.id}")

    def get(self, channel_id: str) -> ChannelPlugin | None:
        return self._channels.get(channel_id)

    def list_channels(self) -> list[ChannelPlugin]:
        ordered = []
        seen = set()
        for cid in CHANNEL_ORDER:
            if cid in self._channels:
                ordered.append(self._channels[cid])
                seen.add(cid)
        for cid, plugin in sorted(self._channels.items()):
            if cid not in seen:
                ordered.append(plugin)
        return ordered

    def list_ids(self) -> list[str]:
        return [p.id for p in self.list_channels()]

    def is_registered(self, channel_id: str) -> bool:
        return channel_id in self._channels


def create_default_registry() -> ChannelRegistry:
    registry = ChannelRegistry()
    # Lazy-load available channels
    try:
        from predator.channels.telegram import TelegramChannel
        registry.register(TelegramChannel())
    except ImportError:
        logger.debug("Telegram channel not available")
    try:
        from predator.channels.discord import DiscordChannel
        registry.register(DiscordChannel())
    except ImportError:
        logger.debug("Discord channel not available")
    try:
        from predator.channels.whatsapp import WhatsAppChannel
        registry.register(WhatsAppChannel())
    except ImportError:
        logger.debug("WhatsApp channel not available")
    try:
        from predator.channels.slack_channel import SlackChannel
        registry.register(SlackChannel())
    except ImportError:
        logger.debug("Slack channel not available")
    try:
        from predator.channels.irc_channel import IRCChannel
        registry.register(IRCChannel())
    except ImportError:
        logger.debug("IRC channel not available")
    try:
        from predator.channels.signal_channel import SignalChannel
        registry.register(SignalChannel())
    except ImportError:
        logger.debug("Signal channel not available")
    try:
        from predator.channels.matrix_channel import MatrixChannel
        registry.register(MatrixChannel())
    except ImportError:
        logger.debug("Matrix channel not available")
    return registry
