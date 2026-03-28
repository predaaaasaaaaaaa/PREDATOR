"""Channel service — orchestrates channels, router, and agent runtime.

This is the missing glue layer that wires:
  Inbound message (Telegram/Discord/etc) -> Router -> Agent Runtime -> Response back to channel
"""

from __future__ import annotations

import asyncio
import logging
from typing import Any, Optional

from predator.agents.runtime import AgentRuntime, AgentResult
from predator.channels.registry import ChannelRegistry, create_default_registry
from predator.channels.router import ChannelRouter
from predator.channels.types import (
    ChannelPlugin,
    InboundMessage,
    MessageContext,
    ReplyPayload,
)
from predator.config.schema import PredatorConfig
from predator.memory.manager import MemoryManager
from predator.sessions.transcript import SessionManager

logger = logging.getLogger(__name__)


class ChannelService:
    """Orchestrates channel integrations with the agent runtime.

    Lifecycle:
    1. start() — discovers configured channels, starts their accounts, begins listening
    2. Inbound messages flow: channel -> router -> _handle_agent_message -> agent runtime -> response
    3. stop() — gracefully stops all channel accounts
    """

    def __init__(
        self,
        config: PredatorConfig,
        agent_factory: Any = None,
        session_manager: Optional[SessionManager] = None,
        memory_manager: Optional[MemoryManager] = None,
    ) -> None:
        self._config = config
        self._agent_factory = agent_factory  # callable(session_id) -> AgentRuntime
        self._session_manager = session_manager or SessionManager()
        self._memory_manager = memory_manager or MemoryManager()
        self._channel_registry: Optional[ChannelRegistry] = None
        self._router: Optional[ChannelRouter] = None
        self._running_accounts: list[tuple[str, str]] = []  # (channel_id, account_id)

    async def _handle_agent_message(self, ctx: MessageContext) -> list[ReplyPayload]:
        """Handle an inbound message by running it through the agent.

        This is the callback passed to ChannelRouter — the core integration point.
        """
        session_id = ctx.session_key
        logger.info(f"Agent request from {ctx.channel}/{ctx.sender_name}: {ctx.body[:100]}")

        try:
            # Get or create session transcript
            transcript = self._session_manager.get_or_create(session_id)
            history = transcript.get_message_history()

            # Create agent runtime via factory
            if self._agent_factory:
                runtime = self._agent_factory(session_id)
            else:
                logger.error("No agent factory configured")
                return [ReplyPayload(text="Agent not available", format="plain")]

            # Run the agent
            result: AgentResult = await runtime.run(
                message=ctx.body_for_agent,
                history=history,
                session_id=session_id,
            )

            # Auto-diary
            try:
                tools_used = []
                for turn in result.turns:
                    for tc in turn.tool_calls:
                        tools_used.append(tc.get("name", ""))
                self._memory_manager.auto_diary(
                    session_id=session_id,
                    message=ctx.body_for_agent,
                    response=result.final_text,
                    tools_used=tools_used,
                    tokens=result.total_tokens,
                )
            except Exception:
                pass

            if not result.final_text:
                return [ReplyPayload(text="[No response from agent]", format="plain")]

            return [ReplyPayload(text=result.final_text, format="markdown")]

        except Exception as e:
            logger.error(f"Agent error for {ctx.channel}/{ctx.sender_name}: {e}")
            return [ReplyPayload(text=f"Error: {e}", format="plain")]

    async def start(self, channel_filter: list[str] | None = None) -> None:
        """Start configured channels and begin listening.

        Args:
            channel_filter: If provided, only start channels whose id is in this list.
                           Pass ["all"] or None to start all configured channels.
        """
        self._channel_registry = create_default_registry()
        self._router = ChannelRouter(
            agent_handler=self._handle_agent_message,
            config=self._config,
        )

        # Normalize filter: None or ["all"] means start everything
        filter_set = None
        if channel_filter and "all" not in channel_filter:
            filter_set = set(channel_filter)

        started = 0
        for plugin in self._channel_registry.list_channels():
            # Apply channel filter
            if filter_set and plugin.id not in filter_set:
                continue

            if not plugin.is_configured(self._config):
                continue

            account_ids = plugin.list_account_ids(self._config) or ["default"]
            for account_id in account_ids:
                try:
                    # Create the on_message callback that routes to our router
                    async def make_on_message(ch=plugin, aid=account_id):
                        async def on_message(msg: InboundMessage):
                            msg.account_id = aid
                            await self._router.handle_inbound(ch, msg)
                        return on_message

                    callback = await make_on_message()
                    await plugin.start_account(
                        account_id=account_id,
                        config=self._config,
                        on_message=callback,
                    )
                    self._running_accounts.append((plugin.id, account_id))
                    started += 1
                    logger.info(f"Channel started: {plugin.id}/{account_id}")
                except Exception as e:
                    logger.error(f"Failed to start channel {plugin.id}/{account_id}: {e}")

        logger.info(f"Channel service started: {started} account(s) active")

    async def stop(self) -> None:
        """Stop all running channel accounts."""
        for channel_id, account_id in self._running_accounts:
            try:
                plugin = self._channel_registry.get(channel_id)
                if plugin:
                    await plugin.stop_account(account_id)
                    logger.info(f"Channel stopped: {channel_id}/{account_id}")
            except Exception as e:
                logger.error(f"Error stopping {channel_id}/{account_id}: {e}")

        self._running_accounts.clear()
        logger.info("Channel service stopped")

    @property
    def active_channels(self) -> list[tuple[str, str]]:
        return list(self._running_accounts)
