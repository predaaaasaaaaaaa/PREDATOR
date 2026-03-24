"""Matrix channel integration — connects to Matrix protocol via matrix-nio.

Uses the matrix-nio library for async Matrix protocol support.
Supports text messages, media uploads, and room-based communication.
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


class MatrixChannel(ChannelPlugin):
    """Matrix protocol integration via matrix-nio."""

    def __init__(self):
        self._clients: dict[str, Any] = {}  # account_id -> AsyncClient
        self._sync_tasks: dict[str, asyncio.Task] = {}
        self._snapshots: dict[str, ChannelAccountSnapshot] = {}
        self._running: dict[str, bool] = {}
        self._configs: dict[str, dict[str, Any]] = {}

    @property
    def id(self) -> str:
        return "matrix"

    @property
    def meta(self) -> ChannelMeta:
        return ChannelMeta(
            id="matrix",
            label="Matrix",
            blurb="Connect to Matrix rooms via a homeserver using matrix-nio.",
            docs_path="/channels/matrix",
            order=7,
        )

    @property
    def capabilities(self) -> ChannelCapabilities:
        return ChannelCapabilities(
            threads=True, reactions=True, polls=False,
            media=True, buttons=False, location=False,
        )

    @property
    def delivery_mode(self) -> DeliveryMode:
        return DeliveryMode.POLLING

    @property
    def text_chunk_limit(self) -> int:
        return 65536

    def list_account_ids(self, config: Any) -> list[str]:
        channels_cfg = getattr(config, "channels", None) or {}
        if isinstance(channels_cfg, dict):
            mx = channels_cfg.get("matrix", {})
        else:
            mx = getattr(channels_cfg, "matrix", {}) or {}
        token = mx.get("access_token", "") if isinstance(mx, dict) else getattr(mx, "access_token", "")
        return ["default"] if token else []

    def resolve_account(self, config: Any, account_id: str | None = None) -> dict[str, Any]:
        channels_cfg = getattr(config, "channels", None) or {}
        if isinstance(channels_cfg, dict):
            mx = channels_cfg.get("matrix", {})
        else:
            mx = getattr(channels_cfg, "matrix", {}) or {}

        if isinstance(mx, dict):
            homeserver_url = mx.get("homeserver_url", "")
            access_token = mx.get("access_token", "")
            user_id = mx.get("user_id", "")
            allowed_rooms = mx.get("allowed_rooms", [])
        else:
            homeserver_url = getattr(mx, "homeserver_url", "")
            access_token = getattr(mx, "access_token", "")
            user_id = getattr(mx, "user_id", "")
            allowed_rooms = getattr(mx, "allowed_rooms", [])

        import os
        homeserver_url = homeserver_url or os.environ.get("MATRIX_HOMESERVER_URL", "")
        access_token = access_token or os.environ.get("MATRIX_ACCESS_TOKEN", "")
        user_id = user_id or os.environ.get("MATRIX_USER_ID", "")

        return {
            "account_id": account_id or "default",
            "enabled": True,
            "homeserver_url": homeserver_url,
            "access_token": access_token,
            "user_id": user_id,
            "allowed_rooms": allowed_rooms,
        }

    def is_configured(self, config: Any, account_id: str | None = None) -> bool:
        acct = self.resolve_account(config, account_id)
        return bool(acct.get("homeserver_url") and acct.get("access_token"))

    async def start_account(self, account_id: str, config: Any, on_message: Callable, abort_signal: Any = None) -> None:
        """Start Matrix sync loop listening for room messages."""
        try:
            from nio import AsyncClient, RoomMessageText, MatrixRoom
        except ImportError:
            logger.error("matrix-nio not installed. Run: pip install matrix-nio")
            return

        acct = self.resolve_account(config, account_id)
        homeserver = acct.get("homeserver_url")
        token = acct.get("access_token")
        user_id = acct.get("user_id")

        if not homeserver or not token:
            logger.error(f"Missing homeserver_url or access_token for Matrix account {account_id}")
            return

        client = AsyncClient(homeserver, user_id)
        client.access_token = token

        self._clients[account_id] = client
        self._configs[account_id] = acct
        self._running[account_id] = True
        self._snapshots[account_id] = ChannelAccountSnapshot(
            account_id=account_id,
            name=user_id or "",
            enabled=True,
            configured=True,
            running=True,
            connected=True,
            last_connected_at=int(time.time()),
        )

        allowed_rooms = acct.get("allowed_rooms", [])

        async def message_callback(room: MatrixRoom, event: RoomMessageText):
            # Skip our own messages
            if event.sender == user_id:
                return
            # Filter by allowed rooms if configured
            if allowed_rooms and room.room_id not in allowed_rooms:
                return
            try:
                msg = self.normalize_message({
                    "room": room,
                    "event": event,
                    "account_id": account_id,
                })
                if msg.body:
                    await on_message(msg)
            except Exception as e:
                logger.error(f"Error processing Matrix message: {e}")

        client.add_event_callback(message_callback, RoomMessageText)

        async def sync_loop():
            logger.info(f"Matrix sync started for {user_id} on {homeserver}")
            # Initial sync to skip old messages
            try:
                await client.sync(timeout=10000, full_state=True)
            except Exception as e:
                logger.debug(f"Matrix initial sync error: {e}")

            while self._running.get(account_id, False):
                try:
                    await client.sync(timeout=30000)
                    snap = self._snapshots.get(account_id)
                    if snap:
                        snap.last_connected_at = int(time.time())
                        snap.last_error = None
                except asyncio.CancelledError:
                    break
                except Exception as e:
                    logger.debug(f"Matrix sync error: {e}")
                    snap = self._snapshots.get(account_id)
                    if snap:
                        snap.last_error = str(e)
                    await asyncio.sleep(5)
            logger.info(f"Matrix sync stopped for {user_id}")

        self._sync_tasks[account_id] = asyncio.create_task(sync_loop())
        logger.info(f"Matrix channel started: {account_id} ({user_id})")

    async def stop_account(self, account_id: str) -> None:
        self._running[account_id] = False
        task = self._sync_tasks.pop(account_id, None)
        if task:
            task.cancel()
            try:
                await task
            except asyncio.CancelledError:
                pass
        client = self._clients.pop(account_id, None)
        if client:
            try:
                await client.close()
            except Exception as e:
                logger.error(f"Error closing Matrix client {account_id}: {e}")
        self._configs.pop(account_id, None)
        snap = self._snapshots.get(account_id)
        if snap:
            snap.running = False
            snap.connected = False

    def normalize_message(self, raw: dict[str, Any]) -> InboundMessage:
        room = raw.get("room")
        event = raw.get("event")
        account_id = raw.get("account_id", "default")

        if not event:
            return InboundMessage(raw=raw)

        sender = getattr(event, "sender", "")
        body = getattr(event, "body", "")
        event_id = getattr(event, "event_id", "")
        timestamp = getattr(event, "server_timestamp", 0)

        room_id = ""
        room_name = ""
        member_count = 0
        if room:
            room_id = getattr(room, "room_id", "")
            room_name = getattr(room, "display_name", "") or getattr(room, "name", "")
            member_count = getattr(room, "member_count", 0)

        # Matrix rooms with >2 members are groups
        chat_type = ChatType.GROUP if member_count > 2 else ChatType.DIRECT

        # Extract display name from sender (@user:server -> user)
        sender_name = sender.split(":")[0].lstrip("@") if sender else ""

        # Handle reply (relates_to with m.in_reply_to)
        reply_to_id = ""
        source = getattr(event, "source", {}) or {}
        content = source.get("content", {}) if isinstance(source, dict) else {}
        relates_to = content.get("m.relates_to", {}) if isinstance(content, dict) else {}
        in_reply_to = relates_to.get("m.in_reply_to", {}) if isinstance(relates_to, dict) else {}
        if isinstance(in_reply_to, dict):
            reply_to_id = in_reply_to.get("event_id", "")

        # Strip reply fallback from body (Matrix prepends > quoted lines)
        if reply_to_id and body.startswith("> "):
            lines = body.split("\n")
            non_quote_lines = []
            past_quote = False
            for line in lines:
                if past_quote:
                    non_quote_lines.append(line)
                elif not line.startswith("> ") and line != ">":
                    past_quote = True
                    if line.strip():
                        non_quote_lines.append(line)
            body = "\n".join(non_quote_lines).strip() or body

        return InboundMessage(
            id=event_id,
            sender_id=sender,
            conversation_id=room_id,
            to=room_id,
            account_id=account_id,
            body=body,
            chat_type=chat_type,
            sender_name=sender_name,
            sender_username=sender,
            reply_to_id=reply_to_id,
            group_subject=room_name,
            timestamp=int(timestamp / 1000) if timestamp > 1e12 else int(timestamp),
            raw=raw,
        )

    async def send_text(self, to: str, text: str, account_id: str | None = None, reply_to_id: str | None = None, thread_id: str | None = None) -> OutboundResult:
        try:
            from nio import AsyncClient
        except ImportError:
            raise RuntimeError("matrix-nio not installed")

        aid = account_id or "default"
        client = self._clients.get(aid)
        if not client:
            raise RuntimeError(f"Matrix account {aid} not started")

        content: dict[str, Any] = {
            "msgtype": "m.text",
            "body": text,
        }

        # Add reply reference
        if reply_to_id:
            content["m.relates_to"] = {
                "m.in_reply_to": {
                    "event_id": reply_to_id,
                }
            }

        # Add thread reference
        if thread_id:
            content.setdefault("m.relates_to", {})
            content["m.relates_to"]["rel_type"] = "m.thread"
            content["m.relates_to"]["event_id"] = thread_id

        response = await client.room_send(
            room_id=to,
            message_type="m.room.message",
            content=content,
        )

        event_id = getattr(response, "event_id", "")
        return OutboundResult(
            channel="matrix",
            message_id=event_id,
            chat_id=to,
            timestamp=int(time.time()),
        )

    async def send_media(self, to: str, caption: str, media_url: str, account_id: str | None = None) -> OutboundResult:
        try:
            from nio import AsyncClient, UploadResponse
            import aiofiles
            import mimetypes
            import os
        except ImportError:
            raise RuntimeError("matrix-nio and aiofiles not installed")

        aid = account_id or "default"
        client = self._clients.get(aid)
        if not client:
            raise RuntimeError(f"Matrix account {aid} not started")

        # Determine content type
        mime_type, _ = mimetypes.guess_type(media_url)
        mime_type = mime_type or "application/octet-stream"
        filename = os.path.basename(media_url)

        # Read file and upload
        file_stat = os.stat(media_url)
        async with aiofiles.open(media_url, "rb") as f:
            file_data = await f.read()

        upload_response, _keys = await client.upload(
            data_provider=file_data,
            content_type=mime_type,
            filename=filename,
            filesize=file_stat.st_size,
        )

        if not isinstance(upload_response, UploadResponse):
            raise RuntimeError(f"Matrix upload failed: {upload_response}")

        content_uri = upload_response.content_uri

        # Determine message type based on MIME
        if mime_type.startswith("image/"):
            msgtype = "m.image"
        elif mime_type.startswith("video/"):
            msgtype = "m.video"
        elif mime_type.startswith("audio/"):
            msgtype = "m.audio"
        else:
            msgtype = "m.file"

        content: dict[str, Any] = {
            "msgtype": msgtype,
            "body": caption or filename,
            "url": content_uri,
            "info": {
                "mimetype": mime_type,
                "size": file_stat.st_size,
            },
        }

        response = await client.room_send(
            room_id=to,
            message_type="m.room.message",
            content=content,
        )

        event_id = getattr(response, "event_id", "")
        return OutboundResult(
            channel="matrix",
            message_id=event_id,
            chat_id=to,
            timestamp=int(time.time()),
        )

    def check_access(self, sender_id: str, config: Any, account_id: str | None = None) -> bool:
        acct = self.resolve_account(config, account_id)
        allowed = acct.get("allowed_rooms", [])
        # Room-level access is enforced in the message callback;
        # individual sender access is open by default.
        return True

    def get_account_snapshot(self, account_id: str, config: Any) -> ChannelAccountSnapshot:
        if account_id in self._snapshots:
            return self._snapshots[account_id]
        acct = self.resolve_account(config, account_id)
        return ChannelAccountSnapshot(
            account_id=account_id,
            name=acct.get("user_id", ""),
            enabled=True,
            configured=bool(acct.get("homeserver_url") and acct.get("access_token")),
        )
