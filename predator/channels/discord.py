"""Discord channel integration — mirrors OpenClaw's Discord plugin.

Uses discord.py for bot integration.
Supports: text, media, reactions, threads, embeds.
"""
from __future__ import annotations

import asyncio
import logging
import time
from typing import Any, Callable

from predator.channels.types import (
    ChannelPlugin, ChannelMeta, ChannelCapabilities, ChatType,
    DeliveryMode, InboundMessage, OutboundResult, ChannelAccountSnapshot,
)

logger = logging.getLogger(__name__)


class DiscordChannel(ChannelPlugin):
    """Discord bot integration via discord.py."""

    def __init__(self):
        self._clients: dict[str, Any] = {}
        self._snapshots: dict[str, ChannelAccountSnapshot] = {}
        self._on_message_handlers: dict[str, Callable] = {}

    @property
    def id(self) -> str:
        return "discord"

    @property
    def meta(self) -> ChannelMeta:
        return ChannelMeta(
            id="discord",
            label="Discord",
            blurb="Create a bot in Discord Developer Portal and connect it to PREDATOR.",
            docs_path="/channels/discord",
            order=2,
        )

    @property
    def capabilities(self) -> ChannelCapabilities:
        return ChannelCapabilities(
            threads=True, reactions=True, polls=True,
            media=True, buttons=True,
        )

    @property
    def delivery_mode(self) -> DeliveryMode:
        return DeliveryMode.DIRECT

    @property
    def text_chunk_limit(self) -> int:
        return 2000

    def list_account_ids(self, config: Any) -> list[str]:
        return list(self._get_accounts(config).keys())

    def _get_accounts(self, config: Any) -> dict:
        channels_cfg = getattr(config, "channels", None) or {}
        if isinstance(channels_cfg, dict):
            dc = channels_cfg.get("discord", {})
        else:
            dc = getattr(channels_cfg, "discord", {}) or {}
        return (dc.get("accounts", {}) if isinstance(dc, dict)
                else getattr(dc, "accounts", {}) or {})

    def resolve_account(self, config: Any, account_id: str | None = None) -> dict[str, Any]:
        import os
        accounts = self._get_accounts(config)
        aid = account_id or "default"
        acct = accounts.get(aid, {}) if isinstance(accounts, dict) else {}
        token = acct.get("token", "") or os.environ.get("DISCORD_BOT_TOKEN", "")
        return {
            "account_id": aid,
            "enabled": acct.get("enabled", True),
            "name": acct.get("name", ""),
            "token": token,
            "allowed_users": acct.get("allowed_users", []),
            "allowed_channels": acct.get("allowed_channels", []),
            "allowed_guilds": acct.get("allowed_guilds", []),
        }

    def is_configured(self, config: Any, account_id: str | None = None) -> bool:
        return bool(self.resolve_account(config, account_id).get("token"))

    async def start_account(self, account_id: str, config: Any, on_message: Callable, abort_signal: Any = None) -> None:
        try:
            import discord
        except ImportError:
            logger.error("discord.py not installed. Run: pip install discord.py")
            return

        acct = self.resolve_account(config, account_id)
        token = acct.get("token")
        if not token:
            logger.error(f"No token for Discord account {account_id}")
            return

        intents = discord.Intents.default()
        intents.message_content = True
        client = discord.Client(intents=intents)
        self._on_message_handlers[account_id] = on_message

        @client.event
        async def on_ready():
            logger.info(f"Discord bot connected: {client.user}")
            self._snapshots[account_id] = ChannelAccountSnapshot(
                account_id=account_id, name=str(client.user),
                enabled=True, configured=True, running=True, connected=True,
                last_connected_at=int(time.time()),
            )

        @client.event
        async def on_message(message):
            if message.author == client.user or message.author.bot:
                return
            handler = self._on_message_handlers.get(account_id)
            if handler:
                msg = self._normalize(message, account_id)
                await handler(msg)

        self._clients[account_id] = client
        asyncio.create_task(client.start(token))

    async def stop_account(self, account_id: str) -> None:
        client = self._clients.pop(account_id, None)
        if client:
            await client.close()
        self._on_message_handlers.pop(account_id, None)
        snap = self._snapshots.get(account_id)
        if snap:
            snap.running = False
            snap.connected = False

    def _normalize(self, message: Any, account_id: str) -> InboundMessage:
        chat_type = ChatType.DIRECT
        if hasattr(message.channel, "guild") and message.channel.guild:
            chat_type = ChatType.GROUP

        reply_to_id = ""
        if message.reference and message.reference.message_id:
            reply_to_id = str(message.reference.message_id)

        media_url, media_type = "", ""
        if message.attachments:
            media_url = message.attachments[0].url
            ct = message.attachments[0].content_type or ""
            media_type = "image" if "image" in ct else "video" if "video" in ct else "file"

        return InboundMessage(
            id=str(message.id),
            sender_id=str(message.author.id),
            conversation_id=str(message.channel.id),
            to=str(message.channel.id),
            account_id=account_id,
            body=message.content or "",
            chat_type=chat_type,
            sender_name=message.author.display_name or message.author.name,
            sender_username=str(message.author),
            reply_to_id=reply_to_id,
            group_subject=getattr(getattr(message.channel, "guild", None), "name", ""),
            timestamp=int(message.created_at.timestamp()),
            media_url=media_url,
            media_type=media_type,
        )

    def normalize_message(self, raw: dict[str, Any]) -> InboundMessage:
        return self._normalize(raw["message"], raw.get("account_id", "default"))

    async def send_text(self, to: str, text: str, account_id: str | None = None,
                        reply_to_id: str | None = None, thread_id: str | None = None) -> OutboundResult:
        import discord
        aid = account_id or "default"
        client = self._clients.get(aid)
        if not client:
            raise RuntimeError(f"Discord account {aid} not started")

        channel = client.get_channel(int(to)) or await client.fetch_channel(int(to))
        kwargs: dict[str, Any] = {"content": text}
        if reply_to_id:
            try:
                ref = await channel.fetch_message(int(reply_to_id))
                kwargs["reference"] = ref
            except Exception:
                pass
        result = await channel.send(**kwargs)
        return OutboundResult(
            channel="discord", message_id=str(result.id), chat_id=to,
            timestamp=int(result.created_at.timestamp()),
        )

    async def send_media(self, to: str, caption: str, media_url: str,
                         account_id: str | None = None) -> OutboundResult:
        import discord
        import httpx
        aid = account_id or "default"
        client = self._clients.get(aid)
        if not client:
            raise RuntimeError(f"Discord account {aid} not started")

        channel = client.get_channel(int(to)) or await client.fetch_channel(int(to))
        async with httpx.AsyncClient() as http:
            resp = await http.get(media_url)
            filename = media_url.split("/")[-1].split("?")[0] or "file"
            file = discord.File(fp=resp.content, filename=filename)
        result = await channel.send(content=caption, file=file)
        return OutboundResult(
            channel="discord", message_id=str(result.id), chat_id=to,
            timestamp=int(result.created_at.timestamp()),
        )

    def check_access(self, sender_id: str, config: Any, account_id: str | None = None) -> bool:
        allowed = self.resolve_account(config, account_id).get("allowed_users", [])
        return not allowed or sender_id in [str(u) for u in allowed]

    def get_account_snapshot(self, account_id: str, config: Any) -> ChannelAccountSnapshot:
        if account_id in self._snapshots:
            return self._snapshots[account_id]
        acct = self.resolve_account(config, account_id)
        return ChannelAccountSnapshot(
            account_id=account_id, name=acct.get("name", ""),
            enabled=acct.get("enabled", True), configured=bool(acct.get("token")),
        )
