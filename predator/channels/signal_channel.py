"""Signal channel integration — connects to Signal messenger via signal-cli JSON-RPC.

Uses signal-cli's JSON-RPC interface (typically on localhost:7583) for
sending and receiving messages. Requires signal-cli to be running in
JSON-RPC mode with a registered phone number.
"""
from __future__ import annotations

import asyncio
import json
import logging
import time
from typing import Any, Callable

from predator.channels.types import (
    ChannelPlugin, ChannelMeta, ChannelCapabilities, ChatType,
    DeliveryMode, InboundMessage, OutboundResult, ChannelAccountSnapshot,
)

logger = logging.getLogger(__name__)

DEFAULT_SIGNAL_CLI_URL = "http://localhost:7583/api/v1/rpc"


class SignalChannel(ChannelPlugin):
    """Signal messenger integration via signal-cli JSON-RPC."""

    def __init__(self):
        self._poll_tasks: dict[str, asyncio.Task] = {}
        self._sessions: dict[str, Any] = {}  # account_id -> aiohttp session
        self._snapshots: dict[str, ChannelAccountSnapshot] = {}
        self._running: dict[str, bool] = {}
        self._configs: dict[str, dict[str, Any]] = {}

    @property
    def id(self) -> str:
        return "signal"

    @property
    def meta(self) -> ChannelMeta:
        return ChannelMeta(
            id="signal",
            label="Signal",
            blurb="Connect to Signal messenger via signal-cli JSON-RPC daemon.",
            docs_path="/channels/signal",
            order=6,
        )

    @property
    def capabilities(self) -> ChannelCapabilities:
        return ChannelCapabilities(
            threads=False, reactions=True, polls=False,
            media=True, buttons=False, location=False,
        )

    @property
    def delivery_mode(self) -> DeliveryMode:
        return DeliveryMode.POLLING

    @property
    def text_chunk_limit(self) -> int:
        return 4096

    def list_account_ids(self, config: Any) -> list[str]:
        channels_cfg = getattr(config, "channels", None) or {}
        if isinstance(channels_cfg, dict):
            sig = channels_cfg.get("signal", {})
        else:
            sig = getattr(channels_cfg, "signal", {}) or {}
        phone = sig.get("phone_number", "") if isinstance(sig, dict) else getattr(sig, "phone_number", "")
        return ["default"] if phone else []

    def resolve_account(self, config: Any, account_id: str | None = None) -> dict[str, Any]:
        channels_cfg = getattr(config, "channels", None) or {}
        if isinstance(channels_cfg, dict):
            sig = channels_cfg.get("signal", {})
        else:
            sig = getattr(channels_cfg, "signal", {}) or {}

        if isinstance(sig, dict):
            signal_cli_url = sig.get("signal_cli_url", "") or DEFAULT_SIGNAL_CLI_URL
            phone_number = sig.get("phone_number", "")
            allowed_contacts = sig.get("allowed_contacts", [])
        else:
            signal_cli_url = getattr(sig, "signal_cli_url", "") or DEFAULT_SIGNAL_CLI_URL
            phone_number = getattr(sig, "phone_number", "")
            allowed_contacts = getattr(sig, "allowed_contacts", [])

        import os
        phone_number = phone_number or os.environ.get("SIGNAL_PHONE_NUMBER", "")
        signal_cli_url = signal_cli_url or os.environ.get("SIGNAL_CLI_URL", DEFAULT_SIGNAL_CLI_URL)

        return {
            "account_id": account_id or "default",
            "enabled": True,
            "signal_cli_url": signal_cli_url,
            "phone_number": phone_number,
            "allowed_contacts": allowed_contacts,
        }

    def is_configured(self, config: Any, account_id: str | None = None) -> bool:
        acct = self.resolve_account(config, account_id)
        return bool(acct.get("phone_number") and acct.get("signal_cli_url"))

    async def _jsonrpc_call(self, url: str, method: str, params: dict[str, Any] | None = None) -> Any:
        """Make a JSON-RPC call to signal-cli."""
        import aiohttp

        payload = {
            "jsonrpc": "2.0",
            "method": method,
            "params": params or {},
            "id": str(int(time.time() * 1000)),
        }

        async with aiohttp.ClientSession() as session:
            async with session.post(url, json=payload, timeout=aiohttp.ClientTimeout(total=30)) as resp:
                result = await resp.json()
                if "error" in result:
                    raise RuntimeError(f"signal-cli RPC error: {result['error']}")
                return result.get("result")

    async def start_account(self, account_id: str, config: Any, on_message: Callable, abort_signal: Any = None) -> None:
        """Start polling signal-cli for incoming messages."""
        try:
            import aiohttp
        except ImportError:
            logger.error("aiohttp not installed. Run: pip install aiohttp")
            return

        acct = self.resolve_account(config, account_id)
        phone = acct.get("phone_number")
        if not phone:
            logger.error(f"No phone number for Signal account {account_id}")
            return

        self._configs[account_id] = acct
        self._running[account_id] = True
        self._snapshots[account_id] = ChannelAccountSnapshot(
            account_id=account_id,
            name=phone,
            enabled=True,
            configured=True,
            running=True,
            connected=True,
            last_connected_at=int(time.time()),
        )

        async def poll_loop():
            url = acct["signal_cli_url"]
            logger.info(f"Signal polling started for {phone} via {url}")
            while self._running.get(account_id, False):
                try:
                    messages = await self._jsonrpc_call(url, "receive", {
                        "account": phone,
                    })
                    if messages:
                        for envelope in (messages if isinstance(messages, list) else [messages]):
                            try:
                                msg = self.normalize_message({
                                    "envelope": envelope,
                                    "account_id": account_id,
                                    "phone_number": phone,
                                })
                                if msg.body:
                                    await on_message(msg)
                            except Exception as e:
                                logger.error(f"Error processing Signal message: {e}")
                except asyncio.CancelledError:
                    break
                except Exception as e:
                    logger.debug(f"Signal poll error: {e}")
                    snap = self._snapshots.get(account_id)
                    if snap:
                        snap.last_error = str(e)
                await asyncio.sleep(1.5)
            logger.info(f"Signal polling stopped for {phone}")

        self._poll_tasks[account_id] = asyncio.create_task(poll_loop())
        logger.info(f"Signal channel started: {account_id} ({phone})")

    async def stop_account(self, account_id: str) -> None:
        self._running[account_id] = False
        task = self._poll_tasks.pop(account_id, None)
        if task:
            task.cancel()
            try:
                await task
            except asyncio.CancelledError:
                pass
        self._configs.pop(account_id, None)
        snap = self._snapshots.get(account_id)
        if snap:
            snap.running = False
            snap.connected = False

    def normalize_message(self, raw: dict[str, Any]) -> InboundMessage:
        envelope = raw.get("envelope", {})
        account_id = raw.get("account_id", "default")
        phone_number = raw.get("phone_number", "")

        source = envelope.get("source", "") or envelope.get("sourceNumber", "")
        source_name = envelope.get("sourceName", "")
        timestamp = envelope.get("timestamp", 0)

        # Extract data message
        data = envelope.get("dataMessage", {}) or {}
        body = data.get("message", "") or data.get("body", "") or ""

        # Group info
        group_info = data.get("groupInfo", {}) or {}
        group_id = group_info.get("groupId", "")
        group_name = group_info.get("groupName", "") or group_info.get("name", "")
        chat_type = ChatType.GROUP if group_id else ChatType.DIRECT

        # Conversation ID: group ID if group message, else sender number
        conversation_id = group_id if group_id else source

        # Quote/reply
        quote = data.get("quote", {}) or {}
        reply_to_id = str(quote.get("id", "")) if quote.get("id") else ""
        reply_to_body = quote.get("text", "") or ""

        # Media attachments
        attachments = data.get("attachments", []) or []
        media_type = ""
        if attachments:
            first = attachments[0] if attachments else {}
            content_type = first.get("contentType", "")
            if content_type.startswith("image/"):
                media_type = "photo"
            elif content_type.startswith("video/"):
                media_type = "video"
            elif content_type.startswith("audio/"):
                media_type = "voice"
            else:
                media_type = "document"

        return InboundMessage(
            id=str(timestamp),
            sender_id=source,
            conversation_id=conversation_id,
            to=phone_number,
            account_id=account_id,
            body=body,
            chat_type=chat_type,
            sender_name=source_name,
            sender_username=source,
            reply_to_id=reply_to_id,
            reply_to_body=reply_to_body,
            group_subject=group_name,
            timestamp=int(timestamp / 1000) if timestamp > 1e12 else int(timestamp),
            media_type=media_type,
            raw=raw,
        )

    async def send_text(self, to: str, text: str, account_id: str | None = None, reply_to_id: str | None = None, thread_id: str | None = None) -> OutboundResult:
        aid = account_id or "default"
        acct = self._configs.get(aid)
        if not acct:
            raise RuntimeError(f"Signal account {aid} not started")

        url = acct["signal_cli_url"]
        phone = acct["phone_number"]

        params: dict[str, Any] = {
            "account": phone,
            "message": text,
        }

        # Determine if 'to' is a group ID or a phone number
        if to.startswith("+") or to.replace("-", "").replace(" ", "").isdigit():
            params["recipient"] = [to]
        else:
            params["groupId"] = to

        if reply_to_id:
            params["quoteTimestamp"] = int(reply_to_id)

        result = await self._jsonrpc_call(url, "send", params)
        ts = result.get("timestamp", 0) if isinstance(result, dict) else int(time.time())

        return OutboundResult(
            channel="signal",
            message_id=str(ts),
            chat_id=to,
            timestamp=int(ts / 1000) if ts > 1e12 else int(ts),
        )

    async def send_media(self, to: str, caption: str, media_url: str, account_id: str | None = None) -> OutboundResult:
        aid = account_id or "default"
        acct = self._configs.get(aid)
        if not acct:
            raise RuntimeError(f"Signal account {aid} not started")

        url = acct["signal_cli_url"]
        phone = acct["phone_number"]

        params: dict[str, Any] = {
            "account": phone,
            "message": caption,
            "attachment": [media_url],
        }

        if to.startswith("+") or to.replace("-", "").replace(" ", "").isdigit():
            params["recipient"] = [to]
        else:
            params["groupId"] = to

        result = await self._jsonrpc_call(url, "send", params)
        ts = result.get("timestamp", 0) if isinstance(result, dict) else int(time.time())

        return OutboundResult(
            channel="signal",
            message_id=str(ts),
            chat_id=to,
            timestamp=int(ts / 1000) if ts > 1e12 else int(ts),
        )

    def check_access(self, sender_id: str, config: Any, account_id: str | None = None) -> bool:
        acct = self.resolve_account(config, account_id)
        allowed = acct.get("allowed_contacts", [])
        if not allowed:
            return True
        return sender_id in [str(c) for c in allowed]

    def get_account_snapshot(self, account_id: str, config: Any) -> ChannelAccountSnapshot:
        if account_id in self._snapshots:
            return self._snapshots[account_id]
        acct = self.resolve_account(config, account_id)
        return ChannelAccountSnapshot(
            account_id=account_id,
            name=acct.get("phone_number", ""),
            enabled=True,
            configured=bool(acct.get("phone_number")),
        )
