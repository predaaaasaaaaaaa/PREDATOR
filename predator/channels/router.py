"""Channel message router — routes inbound messages to agent, delivers responses."""
from __future__ import annotations
import asyncio
import logging
import time
from typing import Any, Callable, Awaitable
from predator.channels.types import (
    ChannelPlugin, InboundMessage, MessageContext, ReplyPayload, OutboundResult
)
from predator.channels.session_key import build_peer_session_key, build_main_session_key

logger = logging.getLogger(__name__)

class ChannelRouter:
    """Routes messages between channels and the agent runtime."""

    def __init__(
        self,
        agent_handler: Callable[[MessageContext], Awaitable[list[ReplyPayload]]],
        config: Any = None,
    ):
        self._agent_handler = agent_handler
        self._config = config
        self._active_conversations: dict[str, asyncio.Task] = {}

    def build_context(self, channel: ChannelPlugin, msg: InboundMessage, agent_id: str = "default") -> MessageContext:
        session_key = build_peer_session_key(
            agent_id=agent_id,
            channel=channel.id,
            peer_id=msg.conversation_id or msg.sender_id,
            chat_type=msg.chat_type.value,
        )
        main_session_key = build_main_session_key(agent_id)
        body_for_agent = msg.body.strip()
        body_for_commands = msg.body.strip()

        return MessageContext(
            channel=channel.id,
            sender_id=msg.sender_id,
            sender_name=msg.sender_name,
            sender_username=msg.sender_username,
            to=msg.to,
            chat_type=msg.chat_type,
            body=msg.body,
            body_for_agent=body_for_agent,
            body_for_commands=body_for_commands,
            reply_to_id=msg.reply_to_id,
            reply_to_body=msg.reply_to_body,
            thread_label=msg.group_subject,
            session_key=session_key,
            main_session_key=main_session_key,
            media_url=msg.media_url,
            media_path=msg.media_path,
            media_type=msg.media_type,
            account_id=msg.account_id,
            raw=msg.raw,
        )

    async def handle_inbound(self, channel: ChannelPlugin, msg: InboundMessage, agent_id: str = "default") -> list[OutboundResult]:
        ctx = self.build_context(channel, msg, agent_id)

        if not channel.check_access(msg.sender_id, self._config, msg.account_id):
            logger.warning(f"Access denied for {msg.sender_id} on {channel.id}")
            return []

        logger.info(f"[{channel.id}] {msg.sender_name or msg.sender_id}: {msg.body[:100]}")

        try:
            payloads = await self._agent_handler(ctx)
        except Exception as e:
            logger.error(f"Agent error: {e}")
            payloads = [ReplyPayload(text=f"Error: {e}", format="plain")]

        results = []
        for payload in payloads:
            try:
                result = await self._deliver_payload(channel, ctx, payload)
                results.extend(result)
            except Exception as e:
                logger.error(f"Delivery error on {channel.id}: {e}")

        return results

    async def _deliver_payload(self, channel: ChannelPlugin, ctx: MessageContext, payload: ReplyPayload) -> list[OutboundResult]:
        results = []
        if payload.media_url:
            try:
                r = await channel.send_media(
                    to=ctx.sender_id if ctx.chat_type == "direct" else ctx.to,
                    caption=payload.text,
                    media_url=payload.media_url,
                    account_id=ctx.account_id,
                )
                results.append(r)
                return results
            except NotImplementedError:
                pass

        chunks = channel.chunk_text(payload.text)
        for i, chunk in enumerate(chunks):
            r = await channel.send_text(
                to=ctx.sender_id if ctx.chat_type == "direct" else ctx.to,
                text=chunk,
                account_id=ctx.account_id,
                reply_to_id=ctx.reply_to_id if i == 0 else None,
                thread_id=ctx.message_thread_id or None,
            )
            results.append(r)
        return results
