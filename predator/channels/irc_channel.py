"""IRC channel integration — mirrors OpenClaw's IRC plugin.

Classic IRC bot for old-school hackers.
"""
from __future__ import annotations

import asyncio
import logging
import os
import time
from typing import Any, Callable

from predator.channels.types import (
    ChannelPlugin, ChannelMeta, ChannelCapabilities, ChatType,
    DeliveryMode, InboundMessage, OutboundResult, ChannelAccountSnapshot,
)

logger = logging.getLogger(__name__)


class IRCChannel(ChannelPlugin):
    """IRC bot integration."""

    def __init__(self):
        self._connections: dict[str, Any] = {}
        self._snapshots: dict[str, ChannelAccountSnapshot] = {}

    @property
    def id(self) -> str:
        return "irc"

    @property
    def meta(self) -> ChannelMeta:
        return ChannelMeta(
            id="irc", label="IRC",
            blurb="Connect to IRC networks for old-school chat integration.",
            order=5,
        )

    @property
    def capabilities(self) -> ChannelCapabilities:
        return ChannelCapabilities()

    @property
    def text_chunk_limit(self) -> int:
        return 512

    def _get_accounts(self, config: Any) -> dict:
        channels_cfg = getattr(config, "channels", None) or {}
        if isinstance(channels_cfg, dict):
            irc = channels_cfg.get("irc", {})
        else:
            irc = getattr(channels_cfg, "irc", {}) or {}
        return (irc.get("accounts", {}) if isinstance(irc, dict)
                else getattr(irc, "accounts", {}) or {})

    def list_account_ids(self, config: Any) -> list[str]:
        return list(self._get_accounts(config).keys())

    def resolve_account(self, config: Any, account_id: str | None = None) -> dict[str, Any]:
        accounts = self._get_accounts(config)
        aid = account_id or "default"
        acct = accounts.get(aid, {}) if isinstance(accounts, dict) else {}
        return {
            "account_id": aid,
            "enabled": acct.get("enabled", True),
            "server": acct.get("server", "") or os.environ.get("IRC_SERVER", ""),
            "port": acct.get("port", 6697),
            "ssl": acct.get("ssl", True),
            "nick": acct.get("nick", "predator-bot"),
            "channels": acct.get("channels", []),
            "password": acct.get("password", ""),
        }

    def is_configured(self, config: Any, account_id: str | None = None) -> bool:
        return bool(self.resolve_account(config, account_id).get("server"))

    async def start_account(self, account_id: str, config: Any, on_message: Callable, abort_signal: Any = None) -> None:
        acct = self.resolve_account(config, account_id)
        server = acct.get("server")
        if not server:
            logger.error(f"No server for IRC account {account_id}")
            return

        port = acct.get("port", 6697)
        use_ssl = acct.get("ssl", True)
        nick = acct.get("nick", "predator-bot")
        channels = acct.get("channels", [])

        async def irc_loop():
            try:
                if use_ssl:
                    import ssl as ssl_mod
                    ctx = ssl_mod.create_default_context()
                    reader, writer = await asyncio.open_connection(server, port, ssl=ctx)
                else:
                    reader, writer = await asyncio.open_connection(server, port)

                def send(msg: str):
                    writer.write(f"{msg}\r\n".encode())

                if acct.get("password"):
                    send(f"PASS {acct['password']}")
                send(f"NICK {nick}")
                send(f"USER {nick} 0 * :PREDATOR Bot")

                self._connections[account_id] = writer
                self._snapshots[account_id] = ChannelAccountSnapshot(
                    account_id=account_id, name=nick,
                    enabled=True, configured=True, running=True, connected=True,
                    last_connected_at=int(time.time()),
                )

                while True:
                    line = await reader.readline()
                    if not line:
                        break
                    text = line.decode("utf-8", errors="ignore").strip()
                    if text.startswith("PING"):
                        send(f"PONG {text[5:]}")
                        continue
                    if " 001 " in text:
                        for ch in channels:
                            send(f"JOIN {ch}")
                    if "PRIVMSG" in text:
                        parts = text.split(" ", 3)
                        if len(parts) >= 4:
                            sender = parts[0].lstrip(":").split("!")[0]
                            target = parts[2]
                            body = parts[3].lstrip(":")
                            chat_type = ChatType.GROUP if target.startswith("#") else ChatType.DIRECT
                            msg = InboundMessage(
                                sender_id=sender,
                                conversation_id=target,
                                to=target,
                                account_id=account_id,
                                body=body,
                                chat_type=chat_type,
                                sender_name=sender,
                                timestamp=int(time.time()),
                            )
                            await on_message(msg)
            except Exception as e:
                logger.error(f"IRC error: {e}")
                snap = self._snapshots.get(account_id)
                if snap:
                    snap.connected = False
                    snap.last_error = str(e)

        asyncio.create_task(irc_loop())
        logger.info(f"IRC connecting: {account_id} -> {server}:{port}")

    async def stop_account(self, account_id: str) -> None:
        writer = self._connections.pop(account_id, None)
        if writer:
            try:
                writer.write(b"QUIT :PREDATOR shutting down\r\n")
                writer.close()
            except Exception:
                pass
        snap = self._snapshots.get(account_id)
        if snap:
            snap.running = False
            snap.connected = False

    def normalize_message(self, raw: dict[str, Any]) -> InboundMessage:
        return InboundMessage(raw=raw)

    async def send_text(self, to: str, text: str, account_id: str | None = None,
                        reply_to_id: str | None = None, thread_id: str | None = None) -> OutboundResult:
        aid = account_id or "default"
        writer = self._connections.get(aid)
        if not writer:
            raise RuntimeError(f"IRC account {aid} not connected")
        for line in text.split("\n"):
            if line.strip():
                writer.write(f"PRIVMSG {to} :{line}\r\n".encode())
        return OutboundResult(channel="irc", chat_id=to, timestamp=int(time.time()))

    async def send_media(self, to: str, caption: str, media_url: str,
                         account_id: str | None = None) -> OutboundResult:
        return await self.send_text(to, f"{caption} {media_url}", account_id)

    def check_access(self, sender_id: str, config: Any, account_id: str | None = None) -> bool:
        return True

    def get_account_snapshot(self, account_id: str, config: Any) -> ChannelAccountSnapshot:
        return self._snapshots.get(account_id, ChannelAccountSnapshot(account_id=account_id))
