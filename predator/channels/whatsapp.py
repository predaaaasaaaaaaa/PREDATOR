"""WhatsApp channel integration — mirrors OpenClaw's WhatsApp plugin.

Uses gateway delivery mode — communicates via HTTP to a WhatsApp bridge
(e.g., whatsapp-web.js, Baileys, or Evolution API).
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


class WhatsAppChannel(ChannelPlugin):
    """WhatsApp integration via gateway bridge."""

    def __init__(self):
        self._snapshots: dict[str, ChannelAccountSnapshot] = {}

    @property
    def id(self) -> str:
        return "whatsapp"

    @property
    def meta(self) -> ChannelMeta:
        return ChannelMeta(
            id="whatsapp",
            label="WhatsApp",
            blurb="Connect via WhatsApp Web bridge (Baileys/Evolution API).",
            docs_path="/channels/whatsapp",
            order=3,
        )

    @property
    def capabilities(self) -> ChannelCapabilities:
        return ChannelCapabilities(
            media=True, polls=True, location=True, reactions=True,
        )

    @property
    def delivery_mode(self) -> DeliveryMode:
        return DeliveryMode.GATEWAY

    @property
    def text_chunk_limit(self) -> int:
        return 4000

    def _get_accounts(self, config: Any) -> dict:
        channels_cfg = getattr(config, "channels", None) or {}
        if isinstance(channels_cfg, dict):
            wa = channels_cfg.get("whatsapp", {})
        else:
            wa = getattr(channels_cfg, "whatsapp", {}) or {}
        return (wa.get("accounts", {}) if isinstance(wa, dict)
                else getattr(wa, "accounts", {}) or {})

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
            "bridge_url": acct.get("bridge_url", "") or os.environ.get("WHATSAPP_BRIDGE_URL", ""),
            "api_key": acct.get("api_key", "") or os.environ.get("WHATSAPP_API_KEY", ""),
            "phone": acct.get("phone", ""),
            "allowed_users": acct.get("allowed_users", []),
        }

    def is_configured(self, config: Any, account_id: str | None = None) -> bool:
        acct = self.resolve_account(config, account_id)
        return bool(acct.get("bridge_url"))

    def _normalize_phone(self, phone: str) -> str:
        """Normalize to E.164 format."""
        phone = phone.strip().replace(" ", "").replace("-", "")
        if not phone.startswith("+"):
            phone = "+" + phone
        return phone

    async def start_account(self, account_id: str, config: Any, on_message: Callable, abort_signal: Any = None) -> None:
        acct = self.resolve_account(config, account_id)
        if not acct.get("bridge_url"):
            logger.error(f"No bridge URL for WhatsApp account {account_id}")
            return

        # Register webhook with bridge for inbound messages
        import httpx
        try:
            async with httpx.AsyncClient() as client:
                await client.post(
                    f"{acct['bridge_url']}/webhook/register",
                    json={"url": f"http://localhost:18789/channels/whatsapp/{account_id}/inbound"},
                    headers={"Authorization": f"Bearer {acct.get('api_key', '')}"},
                    timeout=10,
                )
            self._snapshots[account_id] = ChannelAccountSnapshot(
                account_id=account_id, name=acct.get("name", ""),
                enabled=True, configured=True, running=True, connected=True,
                last_connected_at=int(time.time()),
            )
            logger.info(f"WhatsApp bridge connected: {account_id}")
        except Exception as e:
            logger.error(f"Failed to connect WhatsApp bridge: {e}")
            self._snapshots[account_id] = ChannelAccountSnapshot(
                account_id=account_id, configured=True, last_error=str(e),
            )

    async def stop_account(self, account_id: str) -> None:
        snap = self._snapshots.get(account_id)
        if snap:
            snap.running = False
            snap.connected = False

    def normalize_message(self, raw: dict[str, Any]) -> InboundMessage:
        chat_type = ChatType.GROUP if raw.get("isGroup") else ChatType.DIRECT
        return InboundMessage(
            id=raw.get("id", ""),
            sender_id=raw.get("from", ""),
            conversation_id=raw.get("chatId", raw.get("from", "")),
            to=raw.get("to", ""),
            account_id=raw.get("account_id", "default"),
            body=raw.get("body", ""),
            chat_type=chat_type,
            sender_name=raw.get("senderName", ""),
            group_subject=raw.get("groupName", ""),
            timestamp=raw.get("timestamp", 0),
            media_url=raw.get("mediaUrl", ""),
            media_type=raw.get("mediaType", ""),
            raw=raw,
        )

    async def send_text(self, to: str, text: str, account_id: str | None = None,
                        reply_to_id: str | None = None, thread_id: str | None = None) -> OutboundResult:
        import httpx
        aid = account_id or "default"
        # Resolve bridge from snapshot config
        snap = self._snapshots.get(aid)
        if not snap or not snap.connected:
            raise RuntimeError(f"WhatsApp account {aid} not connected")

        # Send via bridge HTTP API
        async with httpx.AsyncClient() as client:
            resp = await client.post(
                f"{os.environ.get('WHATSAPP_BRIDGE_URL', '')}/message/send",
                json={
                    "to": self._normalize_phone(to),
                    "text": text,
                    "replyTo": reply_to_id,
                },
                timeout=30,
            )
            data = resp.json()

        return OutboundResult(
            channel="whatsapp",
            message_id=data.get("id", ""),
            chat_id=to,
            timestamp=int(time.time()),
        )

    async def send_media(self, to: str, caption: str, media_url: str,
                         account_id: str | None = None) -> OutboundResult:
        import httpx
        async with httpx.AsyncClient() as client:
            resp = await client.post(
                f"{os.environ.get('WHATSAPP_BRIDGE_URL', '')}/message/send-media",
                json={
                    "to": self._normalize_phone(to),
                    "caption": caption,
                    "mediaUrl": media_url,
                },
                timeout=30,
            )
            data = resp.json()
        return OutboundResult(
            channel="whatsapp", message_id=data.get("id", ""), chat_id=to,
            timestamp=int(time.time()),
        )

    def check_access(self, sender_id: str, config: Any, account_id: str | None = None) -> bool:
        allowed = self.resolve_account(config, account_id).get("allowed_users", [])
        if not allowed:
            return True
        normalized = self._normalize_phone(sender_id)
        return normalized in allowed or sender_id in allowed

    def get_account_snapshot(self, account_id: str, config: Any) -> ChannelAccountSnapshot:
        return self._snapshots.get(account_id, ChannelAccountSnapshot(account_id=account_id))
