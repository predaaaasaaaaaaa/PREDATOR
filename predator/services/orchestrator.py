"""Service orchestrator — the main daemon that wires everything together.

Mirrors OpenClaw's server lifecycle: starts gateway, channels, cron, heartbeat,
and connects them all to the agent runtime.

This is what makes PREDATOR a fully autonomous system:
  Gateway (WebSocket RPC)  --|
  Channels (Telegram, etc) --|-->  Agent Runtime  -->  Tools  -->  Results
  Cron (scheduled jobs)    --|
  Heartbeat (monitoring)   --|
"""

from __future__ import annotations

import asyncio
import logging
import signal
from typing import Optional

from predator.agents.runtime import AgentRuntime
from predator.channels.service import ChannelService
from predator.config.loader import load_config
from predator.config.schema import PredatorConfig
from predator.cron.service import CronService
from predator.cron.types import CronJob
from predator.gateway.server import GatewayServer
from predator.heartbeat.runner import HeartbeatConfig, HeartbeatRunner
from predator.hooks.runner import HookRunner
from predator.memory.manager import MemoryManager
from predator.providers.anthropic import AnthropicProvider
from predator.providers.base import BaseProvider
from predator.providers.ollama import OllamaProvider
from predator.providers.openai import OpenAIProvider
from predator.sessions.transcript import SessionManager
from predator.tools.registry import ToolRegistry, create_default_registry

logger = logging.getLogger(__name__)


class Orchestrator:
    """Main service orchestrator — starts and connects all PREDATOR subsystems.

    Usage:
        orchestrator = Orchestrator()
        await orchestrator.start()   # Starts gateway, channels, cron, heartbeat
        await orchestrator.wait()    # Blocks until shutdown signal
        await orchestrator.stop()    # Graceful shutdown
    """

    def __init__(self, config: Optional[PredatorConfig] = None) -> None:
        self._config = config or load_config()
        self._registry: Optional[ToolRegistry] = None
        self._provider: Optional[BaseProvider] = None
        self._hook_runner = HookRunner()
        self._session_manager = SessionManager()
        self._memory_manager = MemoryManager()

        self._gateway: Optional[GatewayServer] = None
        self._channel_service: Optional[ChannelService] = None
        self._cron_service: Optional[CronService] = None
        self._heartbeat: Optional[HeartbeatRunner] = None

        self._shutdown_event = asyncio.Event()

    def _resolve_provider(self) -> BaseProvider:
        """Resolve LLM provider from config — reads profiles for proper initialization."""
        providers_config = self._config.providers
        default = providers_config.default

        if default == "anthropic":
            profile = providers_config.profiles.get("anthropic")
            return AnthropicProvider(
                api_key=profile.api_key if profile else None,
                base_url=profile.base_url if profile else None,
                default_model=profile.model or self._config.agent.model if profile else self._config.agent.model,
            )
        elif default == "openai":
            profile = providers_config.profiles.get("openai")
            return OpenAIProvider(
                api_key=profile.api_key if profile else None,
                base_url=profile.base_url if profile else None,
            )
        elif default == "ollama":
            profile = providers_config.profiles.get("ollama")
            return OllamaProvider(
                base_url=profile.base_url if profile else "http://localhost:11434",
                default_model=profile.model if profile else "llama3.1",
            )
        elif default == "openrouter":
            from predator.providers.openrouter import OpenRouterProvider
            profile = providers_config.profiles.get("openrouter")
            return OpenRouterProvider(
                api_key=profile.api_key if profile else None,
            )
        else:
            return AnthropicProvider(default_model=self._config.agent.model)

    def _create_agent_runtime(self, session_id: str = "main") -> AgentRuntime:
        """Factory that creates an AgentRuntime for a given session."""
        transcript = self._session_manager.get_or_create(session_id)
        return AgentRuntime(
            provider=self._provider,
            registry=self._registry,
            config=self._config,
            hook_runner=self._hook_runner,
            transcript=transcript,
        )

    async def _handle_cron_job(self, job: CronJob) -> str:
        """Cron job handler — runs the job's message through an agent."""
        session_id = f"cron:{job.id}"
        runtime = self._create_agent_runtime(session_id)
        result = await runtime.run(
            message=job.payload.message,
            session_id=session_id,
        )
        logger.info(f"Cron job {job.name} completed: {result.stopped_reason}")
        return result.final_text

    async def _handle_heartbeat_agent(self, prompt: str) -> str:
        """Heartbeat handler — runs the heartbeat prompt through an agent."""
        session_id = "heartbeat:main"
        runtime = self._create_agent_runtime(session_id)
        result = await runtime.run(message=prompt, session_id=session_id)
        return result.final_text

    async def _handle_heartbeat_deliver(self, message: str, to: str) -> None:
        """Heartbeat delivery — send alert through a channel."""
        if self._channel_service and self._channel_service.active_channels:
            # Try to deliver through first active channel
            # In production, this would use the heartbeat config's target channel
            logger.info(f"Heartbeat alert: {message[:200]}")
        else:
            logger.warning(f"Heartbeat alert (no channels): {message[:200]}")

    async def start(
        self,
        enable_gateway: bool = True,
        enable_channels: bool = True,
        enable_cron: bool = True,
        enable_heartbeat: bool = True,
    ) -> None:
        """Start all enabled services."""
        logger.info("Orchestrator starting...")

        # Core initialization
        self._registry = create_default_registry()
        self._provider = self._resolve_provider()

        if not self._provider.is_configured():
            logger.warning("No LLM provider configured -- agent calls will fail")

        # --- Gateway ---
        if enable_gateway:
            self._gateway = GatewayServer(config=self._config)
            # Gateway runs in its own task (it has its own event loop management)
            asyncio.create_task(self._run_gateway())
            logger.info("Gateway service queued")

        # --- Channels ---
        if enable_channels:
            self._channel_service = ChannelService(
                config=self._config,
                agent_factory=self._create_agent_runtime,
                session_manager=self._session_manager,
                memory_manager=self._memory_manager,
            )
            try:
                await self._channel_service.start()
            except Exception as e:
                logger.error(f"Channel service failed to start: {e}")

        # --- Cron ---
        if enable_cron:
            self._cron_service = CronService(
                job_handler=self._handle_cron_job,
            )
            try:
                await self._cron_service.start()
            except Exception as e:
                logger.error(f"Cron service failed to start: {e}")

        # --- Heartbeat ---
        if enable_heartbeat:
            hb_config = HeartbeatConfig(
                interval_ms=self._config.heartbeat.interval_ms
                if hasattr(self._config, "heartbeat") and hasattr(self._config.heartbeat, "interval_ms")
                else 30 * 60 * 1000,
            )
            self._heartbeat = HeartbeatRunner(
                config=hb_config,
                agent_handler=self._handle_heartbeat_agent,
                deliver_handler=self._handle_heartbeat_deliver,
                workspace_dir=str(self._config.workspace_dir)
                if hasattr(self._config, "workspace_dir")
                else "",
            )
            try:
                await self._heartbeat.start()
            except Exception as e:
                logger.error(f"Heartbeat failed to start: {e}")

        logger.info(
            f"Orchestrator running: "
            f"gateway={'on' if enable_gateway else 'off'}, "
            f"channels={len(self._channel_service.active_channels) if self._channel_service else 0}, "
            f"cron={'on' if enable_cron else 'off'}, "
            f"heartbeat={'on' if enable_heartbeat else 'off'}"
        )

    async def _run_gateway(self) -> None:
        """Run the gateway server in a background task."""
        try:
            await self._gateway.start()
        except asyncio.CancelledError:
            pass
        except Exception as e:
            logger.error(f"Gateway error: {e}")

    async def wait(self) -> None:
        """Wait until shutdown signal."""
        loop = asyncio.get_event_loop()
        for sig in (signal.SIGINT, signal.SIGTERM):
            try:
                loop.add_signal_handler(sig, self._shutdown_event.set)
            except NotImplementedError:
                # Windows doesn't support add_signal_handler
                pass
        await self._shutdown_event.wait()

    def request_shutdown(self) -> None:
        """Request graceful shutdown (callable from any context)."""
        self._shutdown_event.set()

    async def stop(self) -> None:
        """Gracefully stop all services."""
        logger.info("Orchestrator stopping...")

        if self._heartbeat:
            await self._heartbeat.stop()

        if self._cron_service:
            await self._cron_service.stop()

        if self._channel_service:
            await self._channel_service.stop()

        if self._gateway:
            await self._gateway.stop()

        logger.info("Orchestrator stopped")


async def run_orchestrator(
    config: Optional[PredatorConfig] = None,
    enable_gateway: bool = True,
    enable_channels: bool = True,
    enable_cron: bool = True,
    enable_heartbeat: bool = True,
) -> None:
    """Convenience function to run the full orchestrator."""
    orch = Orchestrator(config)
    await orch.start(
        enable_gateway=enable_gateway,
        enable_channels=enable_channels,
        enable_cron=enable_cron,
        enable_heartbeat=enable_heartbeat,
    )
    try:
        await orch.wait()
    finally:
        await orch.stop()
