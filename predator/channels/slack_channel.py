"""Slack channel integration — mirrors OpenClaw's Slack plugin.

Uses slack_sdk for Socket Mode and Web API.
"""
from __future__ import annotations

import logging
import os
import time
from typing import Any, Callable

from predator.channels.types import (
    ChannelPlugin, ChannelMeta, ChannelCapabilities, ChatType,
    DeliveryMode, InboundMessage, OutboundResult, ChannelAccountSnapshot,
)

logger = logging.getLogger(__name__)


class SlackChannel(ChannelPlugin):
    """Slack bot via Socket Mode."""

    def __init__(self):
        self._clients: dict[str, Any] = {}
        self._snapshots: dict[str, ChannelAccountSnapshot] = {}

    @property
    def id(self) -> str:
        return "slack"

    @property
    def meta(self) -> ChannelMeta:
        return ChannelMeta(
            id="slack", label="Slack",
            blurb="Create a Slack app with Socket Mode and connect to PREDATOR.",
            order=4,
        )

    @property
    def capabilities(self) -> ChannelCapabilities:
        return ChannelCapabilities(threads=True, reactions=True, media=True, buttons=True)

    @property
    def text_chunk_limit(self) -> int:
        return 4000

    def _get_accounts(self, config: Any) -> dict:
        channels_cfg = getattr(config, "channels", None) or {}
        if isinstance(channels_cfg, dict):
            sl = channels_cfg.get("slack", {})
        else:
            sl = getattr(channels_cfg, "slack", {}) or {}
        return (sl.get("accounts", {}) if isinstance(sl, dict)
                else getattr(sl, "accounts", {}) or {})

    def list_account_ids(self, config: Any) -> list[str]:
        return list(self._get_accounts(config).keys())

    def resolve_account(self, config: Any, account_id: str | None = None) -> dict[str, Any]:
        accounts = self._get_accounts(config)
        aid = account_id or "default"
        acct = accounts.get(aid, {}) if isinstance(accounts, dict) else {}
        return {
            "account_id": aid,
            "enabled": acct.get("enabled", True),
            "name": acct.get("name", ""),
            "bot_token": acct.get("bot_token", "") or os.environ.get("SLACK_BOT_TOKEN", ""),
            "app_token": acct.get("app_token", "") or os.environ.get("SLACK_APP_TOKEN", ""),
            "allowed_users": acct.get("allowed_users", []),
            "allowed_channels": acct.get("allowed_channels", []),
        }

    def is_configured(self, config: Any, account_id: str | None = None) -> bool:
        acct = self.resolve_account(config, account_id)
        return bool(acct.get("bot_token") and acct.get("app_token"))

    async def start_account(self, account_id: str, config: Any, on_message: Callable, abort_signal: Any = None) -> None:
        try:
            from slack_sdk.socket_mode.aiohttp import SocketModeClient
            from slack_sdk.web.async_client import AsyncWebClient
        except ImportError:
            logger.error("slack_sdk not installed. Run: pip install slack_sdk aiohttp")
            return

        acct = self.resolve_account(config, account_id)
        bot_token = acct.get("bot_token")
        app_token = acct.get("app_token")
        if not bot_token or not app_token:
            logger.error(f"Missing tokens for Slack account {account_id}")
            return

        web_client = AsyncWebClient(token=bot_token)
        socket_client = SocketModeClient(app_token=app_token, web_client=web_client)

        async def handle_event(client, req):
            if req.type == "events_api" and req.payload.get("event", {}).get("type") == "message":
                event = req.payload["event"]
                if event.get("bot_id"):
                    return
                msg = InboundMessage(
                    id=event.get("ts", ""),
                    sender_id=event.get("user", ""),
                    conversation_id=event.get("channel", ""),
                    to=event.get("channel", ""),
                    account_id=account_id,
                    body=event.get("text", ""),
                    chat_type=ChatType.GROUP if event.get("channel_type") != "im" else ChatType.DIRECT,
                    reply_to_id=event.get("thread_ts", ""),
                    timestamp=int(float(event.get("ts", "0"))),
                )
                await on_message(msg)
            await client.send_socket_mode_response({"envelope_id": req.envelope_id})

        socket_client.socket_mode_request_listeners.append(handle_event)
        self._clients[account_id] = {"socket": socket_client, "web": web_client}
        await socket_client.connect()
        self._snapshots[account_id] = ChannelAccountSnapshot(
            account_id=account_id, name=acct.get("name", ""),
            enabled=True, configured=True, running=True, connected=True,
            last_connected_at=int(time.time()),
        )
        logger.info(f"Slack bot connected: {account_id}")

    async def stop_account(self, account_id: str) -> None:
        clients = self._clients.pop(account_id, None)
        if clients:
            await clients["socket"].disconnect()
        snap = self._snapshots.get(account_id)
        if snap:
            snap.running = False
            snap.connected = False

    def normalize_message(self, raw: dict[str, Any]) -> InboundMessage:
        return InboundMessage(raw=raw)

    async def send_text(self, to: str, text: str, account_id: str | None = None,
                        reply_to_id: str | None = None, thread_id: str | None = None) -> OutboundResult:
        aid = account_id or "default"
        clients = self._clients.get(aid)
        if not clients:
            raise RuntimeError(f"Slack account {aid} not started")

        kwargs = {"channel": to, "text": text}
        if thread_id or reply_to_id:
            kwargs["thread_ts"] = thread_id or reply_to_id

        resp = await clients["web"].chat_postMessage(**kwargs)
        return OutboundResult(
            channel="slack", message_id=resp.get("ts", ""), chat_id=to,
            timestamp=int(time.time()),
        )

    async def send_media(self, to: str, caption: str, media_url: str,
                         account_id: str | None = None) -> OutboundResult:
        aid = account_id or "default"
        clients = self._clients.get(aid)
        if not clients:
            raise RuntimeError(f"Slack account {aid} not started")
        await clients["web"].chat_postMessage(channel=to, text=f"{caption}\n{media_url}")
        return OutboundResult(channel="slack", chat_id=to, timestamp=int(time.time()))

    def check_access(self, sender_id: str, config: Any, account_id: str | None = None) -> bool:
        allowed = self.resolve_account(config, account_id).get("allowed_users", [])
        return not allowed or sender_id in allowed

    def get_account_snapshot(self, account_id: str, config: Any) -> ChannelAccountSnapshot:
        return self._snapshots.get(account_id, ChannelAccountSnapshot(account_id=account_id))
