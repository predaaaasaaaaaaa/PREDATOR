"""Telegram channel integration — mirrors OpenClaw's Telegram plugin.

Uses python-telegram-bot library for both polling and webhook modes.
Supports: text, media, replies, threads, groups, commands.
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


class TelegramChannel(ChannelPlugin):
    """Telegram bot integration via python-telegram-bot."""

    def __init__(self):
        self._apps: dict[str, Any] = {}  # account_id -> Application
        self._snapshots: dict[str, ChannelAccountSnapshot] = {}

    @property
    def id(self) -> str:
        return "telegram"

    @property
    def meta(self) -> ChannelMeta:
        return ChannelMeta(
            id="telegram",
            label="Telegram",
            blurb="Register a bot with @BotFather and connect it to PREDATOR.",
            docs_path="/channels/telegram",
            order=1,
        )

    @property
    def capabilities(self) -> ChannelCapabilities:
        return ChannelCapabilities(
            threads=True, reactions=True, polls=True,
            media=True, buttons=True, location=True,
        )

    @property
    def delivery_mode(self) -> DeliveryMode:
        return DeliveryMode.DIRECT

    @property
    def text_chunk_limit(self) -> int:
        return 4096

    def list_account_ids(self, config: Any) -> list[str]:
        channels_cfg = getattr(config, "channels", None) or {}
        if isinstance(channels_cfg, dict):
            tg = channels_cfg.get("telegram", {})
        else:
            tg = getattr(channels_cfg, "telegram", {}) or {}
        accounts = tg.get("accounts", {}) if isinstance(tg, dict) else getattr(tg, "accounts", {}) or {}
        return list(accounts.keys()) if isinstance(accounts, dict) else []

    def resolve_account(self, config: Any, account_id: str | None = None) -> dict[str, Any]:
        accounts = self._get_accounts(config)
        aid = account_id or "default"
        acct = accounts.get(aid, {})
        import os
        token = acct.get("token", "") or os.environ.get("TELEGRAM_BOT_TOKEN", "")
        return {
            "account_id": aid,
            "enabled": acct.get("enabled", True),
            "name": acct.get("name", ""),
            "token": token,
            "token_source": "env" if not acct.get("token") else "config",
            "webhook_url": acct.get("webhook_url", ""),
            "allowed_users": acct.get("allowed_users", []),
            "allowed_groups": acct.get("allowed_groups", []),
        }

    def _get_accounts(self, config: Any) -> dict:
        channels_cfg = getattr(config, "channels", None) or {}
        if isinstance(channels_cfg, dict):
            tg = channels_cfg.get("telegram", {})
        else:
            tg = getattr(channels_cfg, "telegram", {}) or {}
        return (tg.get("accounts", {}) if isinstance(tg, dict) else getattr(tg, "accounts", {}) or {})

    def is_configured(self, config: Any, account_id: str | None = None) -> bool:
        acct = self.resolve_account(config, account_id)
        return bool(acct.get("token"))

    async def start_account(self, account_id: str, config: Any, on_message: Callable, abort_signal: Any = None) -> None:
        """Start Telegram bot polling for an account."""
        try:
            from telegram import Update
            from telegram.ext import Application, MessageHandler, CommandHandler, filters
        except ImportError:
            logger.error("python-telegram-bot not installed. Run: pip install python-telegram-bot")
            return

        acct = self.resolve_account(config, account_id)
        token = acct.get("token")
        if not token:
            logger.error(f"No token for Telegram account {account_id}")
            return

        app = Application.builder().token(token).build()

        async def handle_message(update: Update, context):
            if not update.message or not update.message.text:
                return
            msg = self.normalize_message({
                "update": update,
                "account_id": account_id,
            })
            await on_message(msg)

        async def handle_command(update: Update, context):
            if not update.message:
                return
            text = update.message.text or ""
            msg = self.normalize_message({
                "update": update,
                "account_id": account_id,
            })
            await on_message(msg)

        app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))
        app.add_handler(CommandHandler("start", handle_command))
        app.add_handler(CommandHandler("help", handle_command))
        app.add_handler(MessageHandler(filters.COMMAND, handle_command))

        self._apps[account_id] = app
        self._snapshots[account_id] = ChannelAccountSnapshot(
            account_id=account_id,
            name=acct.get("name", ""),
            enabled=True,
            configured=True,
            running=True,
            connected=True,
            last_connected_at=int(time.time()),
        )

        logger.info(f"Starting Telegram bot: {account_id}")
        await app.initialize()
        await app.start()
        await app.updater.start_polling(drop_pending_updates=True)
        logger.info(f"Telegram bot {account_id} is polling")

    async def stop_account(self, account_id: str) -> None:
        app = self._apps.pop(account_id, None)
        if app:
            try:
                await app.updater.stop()
                await app.stop()
                await app.shutdown()
            except Exception as e:
                logger.error(f"Error stopping Telegram {account_id}: {e}")
        snap = self._snapshots.get(account_id)
        if snap:
            snap.running = False
            snap.connected = False

    def normalize_message(self, raw: dict[str, Any]) -> InboundMessage:
        update = raw.get("update")
        account_id = raw.get("account_id", "default")
        msg = update.message if update else None
        if not msg:
            return InboundMessage(raw=raw)

        chat = msg.chat
        user = msg.from_user
        chat_type = ChatType.DIRECT
        if chat.type in ("group", "supergroup"):
            chat_type = ChatType.GROUP
        elif chat.type == "channel":
            chat_type = ChatType.CHANNEL

        media_url = ""
        media_type = ""
        if msg.photo:
            media_type = "photo"
        elif msg.document:
            media_type = "document"
        elif msg.voice:
            media_type = "voice"
        elif msg.video:
            media_type = "video"

        reply_to_id = ""
        reply_to_body = ""
        if msg.reply_to_message:
            reply_to_id = str(msg.reply_to_message.message_id)
            reply_to_body = msg.reply_to_message.text or ""

        thread_id = ""
        if msg.message_thread_id:
            thread_id = str(msg.message_thread_id)

        return InboundMessage(
            id=str(msg.message_id),
            sender_id=str(user.id) if user else "",
            conversation_id=str(chat.id),
            to=str(chat.id),
            account_id=account_id,
            body=msg.text or msg.caption or "",
            chat_type=chat_type,
            sender_name=f"{user.first_name or ''} {user.last_name or ''}".strip() if user else "",
            sender_username=user.username or "" if user else "",
            reply_to_id=reply_to_id,
            reply_to_body=reply_to_body,
            group_subject=chat.title or "",
            timestamp=int(msg.date.timestamp()) if msg.date else 0,
            media_url=media_url,
            media_type=media_type,
            raw={"message_thread_id": thread_id},
        )

    async def send_text(self, to: str, text: str, account_id: str | None = None, reply_to_id: str | None = None, thread_id: str | None = None) -> OutboundResult:
        try:
            from telegram import Bot
            from telegram.constants import ParseMode
        except ImportError:
            raise RuntimeError("python-telegram-bot not installed")

        aid = account_id or "default"
        app = self._apps.get(aid)
        if not app:
            raise RuntimeError(f"Telegram account {aid} not started")

        bot: Bot = app.bot
        kwargs: dict[str, Any] = {
            "chat_id": int(to),
            "text": text,
            "parse_mode": ParseMode.HTML,
        }
        if reply_to_id:
            kwargs["reply_to_message_id"] = int(reply_to_id)
        if thread_id:
            kwargs["message_thread_id"] = int(thread_id)

        result = await bot.send_message(**kwargs)
        return OutboundResult(
            channel="telegram",
            message_id=str(result.message_id),
            chat_id=to,
            timestamp=int(result.date.timestamp()) if result.date else 0,
        )

    async def send_media(self, to: str, caption: str, media_url: str, account_id: str | None = None) -> OutboundResult:
        try:
            from telegram import Bot
            from telegram.constants import ParseMode
        except ImportError:
            raise RuntimeError("python-telegram-bot not installed")

        aid = account_id or "default"
        app = self._apps.get(aid)
        if not app:
            raise RuntimeError(f"Telegram account {aid} not started")

        bot: Bot = app.bot
        result = await bot.send_document(
            chat_id=int(to),
            document=media_url,
            caption=caption,
            parse_mode=ParseMode.HTML,
        )
        return OutboundResult(
            channel="telegram",
            message_id=str(result.message_id),
            chat_id=to,
            timestamp=int(result.date.timestamp()) if result.date else 0,
        )

    def check_access(self, sender_id: str, config: Any, account_id: str | None = None) -> bool:
        acct = self.resolve_account(config, account_id)
        allowed = acct.get("allowed_users", [])
        if not allowed:
            return True  # Open access
        return sender_id in [str(u) for u in allowed]

    def get_account_snapshot(self, account_id: str, config: Any) -> ChannelAccountSnapshot:
        if account_id in self._snapshots:
            return self._snapshots[account_id]
        acct = self.resolve_account(config, account_id)
        return ChannelAccountSnapshot(
            account_id=account_id,
            name=acct.get("name", ""),
            enabled=acct.get("enabled", True),
            configured=bool(acct.get("token")),
        )
