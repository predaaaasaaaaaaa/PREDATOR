"""Gateway WebSocket server — mirrors OpenClaw's server.impl.ts.

The control plane for PREDATOR:
- WebSocket server for CLI and UI clients
- Method-based RPC for agent operations
- Session management
- Plugin and hook orchestration
- Health monitoring
"""

from __future__ import annotations

import asyncio
import json
import time
from typing import Any, Optional, Set

import websockets
from websockets.server import WebSocketServerProtocol

from predator.agents.lanes import CommandLane
from predator.agents.runtime import AgentRuntime, AgentResult
from predator.agents.subagent import SubagentSpawner, SubagentRegistry, set_spawner
from predator.config.loader import load_config
from predator.config.schema import PredatorConfig
from predator.gateway.auth import GatewayAuth
from predator.gateway.rate_limit import RateLimiter, RateLimitConfig
from predator.gateway.protocol import (
    Frame,
    FrameType,
    create_event,
    create_response,
)
from predator.hooks.runner import HookRunner
from predator.plugins.loader import PluginLoader
from predator.process.supervisor import ProcessSupervisor
from predator.providers.anthropic import AnthropicProvider
from predator.providers.base import BaseProvider
from predator.providers.ollama import OllamaProvider
from predator.providers.openai import OpenAIProvider
from predator.sessions.transcript import SessionManager
from predator.tools.registry import ToolRegistry, create_default_registry
from predator.utils.logger import get_logger, setup_logging
from predator.utils.net import DEFAULT_GATEWAY_HOST, DEFAULT_GATEWAY_PORT

log = get_logger("gateway.server")


class GatewayServer:
    """PREDATOR Gateway — WebSocket control plane.

    Mirrors OpenClaw's gateway architecture:
    - WebSocket RPC server
    - Agent runtime management
    - Session orchestration
    - Plugin lifecycle management
    - Process supervision
    - Health monitoring
    """

    def __init__(self, config: Optional[PredatorConfig] = None) -> None:
        self._config = config or load_config()
        self._auth = GatewayAuth(
            token=self._config.gateway.token,
            password=self._config.gateway.password,
        )
        self._clients: Set[WebSocketServerProtocol] = set()
        self._registry: Optional[ToolRegistry] = None
        self._provider: Optional[BaseProvider] = None
        self._hook_runner = HookRunner()
        self._plugin_loader = PluginLoader()
        self._session_manager = SessionManager()
        self._process_supervisor = ProcessSupervisor()
        self._rate_limiter = RateLimiter(RateLimitConfig(
            requests_per_minute=self._config.security.max_tool_calls_per_minute
            if hasattr(self._config, 'security') else 60,
        ))
        self._started_at: Optional[float] = None
        self._server = None
        self._health_server = None

        # Subagent orchestration
        self._subagent_registry = SubagentRegistry()
        self._subagent_spawner = SubagentSpawner(
            registry=self._subagent_registry,
            announce_callback=self._announce_subagent_result,
        )
        set_spawner(self._subagent_spawner)

    def _resolve_provider(self) -> BaseProvider:
        """Resolve the LLM provider based on config."""
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
        else:
            return AnthropicProvider()

    async def _handle_connection(self, ws: WebSocketServerProtocol) -> None:
        """Handle a new WebSocket connection."""
        self._clients.add(ws)
        client_addr = ws.remote_address
        log.info(f"Client connected: {client_addr}")

        try:
            async for raw_message in ws:
                try:
                    frame = Frame.from_json(raw_message)
                    await self._handle_frame(ws, frame)
                except json.JSONDecodeError:
                    await ws.send(
                        create_response("", error="Invalid JSON").to_json()
                    )
                except Exception as e:
                    log.error(f"Error handling frame: {e}")
                    await ws.send(
                        create_response("", error=str(e)).to_json()
                    )
        finally:
            self._clients.discard(ws)
            log.info(f"Client disconnected: {client_addr}")

    async def _handle_frame(self, ws: WebSocketServerProtocol, frame: Frame) -> None:
        """Route a frame to the appropriate handler."""
        if frame.type != FrameType.REQUEST:
            return

        # Rate limiting
        client_id = str(ws.remote_address) if ws.remote_address else "unknown"
        allowed, reason = self._rate_limiter.check(client_id)
        if not allowed:
            await ws.send(create_response(frame.id, error=f"Rate limited: {reason}").to_json())
            return

        method = frame.method
        params = frame.params

        # Method router — mirrors OpenClaw's server-methods/
        handlers = {
            "health": self._handle_health,
            "agent": self._handle_agent,
            "config.get": self._handle_config_get,
            "config.set": self._handle_config_set,
            "sessions.list": self._handle_sessions_list,
            "sessions.delete": self._handle_sessions_delete,
            "tools.list": self._handle_tools_list,
            "process.list": self._handle_process_list,
            "process.kill": self._handle_process_kill,
            "plugins.list": self._handle_plugins_list,
            "subagents.list": self._handle_subagents_list,
            "subagents.kill": self._handle_subagents_kill,
            "subagents.wait": self._handle_subagents_wait,
        }

        handler = handlers.get(method)
        if handler:
            try:
                result = await handler(params)
                await ws.send(create_response(frame.id, result=result).to_json())
            except Exception as e:
                await ws.send(create_response(frame.id, error=str(e)).to_json())
        else:
            await ws.send(
                create_response(frame.id, error=f"Unknown method: {method}").to_json()
            )

    # --- RPC Method Handlers ---

    async def _handle_health(self, params: dict) -> dict:
        """Health check endpoint."""
        uptime = time.time() - self._started_at if self._started_at else 0
        return {
            "status": "ok",
            "version": "1.0.0",
            "uptime": round(uptime, 2),
            "provider": self._provider.provider_type.value if self._provider else "none",
            "provider_configured": self._provider.is_configured() if self._provider else False,
            "tools_count": self._registry.count if self._registry else 0,
            "active_processes": self._process_supervisor.active_count,
            "clients": len(self._clients),
        }

    async def _handle_agent(self, params: dict) -> dict:
        """Run an agent turn — the core RPC method."""
        message = params.get("message", "")
        session_id = params.get("session_id", "main")
        agent_id = params.get("agent_id", "default")

        if not message:
            return {"error": "No message provided"}

        # Get or create session
        transcript = self._session_manager.get_or_create(session_id)
        history = transcript.get_message_history()

        # Create agent runtime
        runtime = AgentRuntime(
            provider=self._provider,
            registry=self._registry,
            config=self._config,
            hook_runner=self._hook_runner,
            transcript=transcript,
        )

        # Run agent
        result: AgentResult = await runtime.run(
            message=message,
            history=history,
            session_id=session_id,
        )

        return {
            "text": result.final_text,
            "turns": len(result.turns),
            "total_tokens": result.total_tokens,
            "elapsed": round(result.total_elapsed, 2),
            "stopped_reason": result.stopped_reason,
        }

    async def _handle_config_get(self, params: dict) -> dict:
        return self._config.model_dump(exclude_none=True)

    async def _handle_config_set(self, params: dict) -> dict:
        # Simplified — just reload config
        self._config = load_config(force_reload=True)
        return {"status": "reloaded"}

    async def _handle_sessions_list(self, params: dict) -> dict:
        sessions = self._session_manager.list_sessions()
        return {"sessions": sessions}

    async def _handle_sessions_delete(self, params: dict) -> dict:
        session_id = params.get("session_id", "")
        deleted = self._session_manager.delete_session(session_id)
        return {"deleted": deleted}

    async def _handle_tools_list(self, params: dict) -> dict:
        if self._registry:
            tools = [
                {"name": t.name, "category": t.category.value, "description": t.description[:100]}
                for t in self._registry.get_all()
            ]
            return {"tools": tools, "count": len(tools)}
        return {"tools": [], "count": 0}

    async def _handle_process_list(self, params: dict) -> dict:
        return self._process_supervisor.summary()

    async def _handle_process_kill(self, params: dict) -> dict:
        from predator.process.executor import kill_process

        pid = params.get("pid", 0)
        if pid:
            killed = await kill_process(pid)
            return {"killed": killed, "pid": pid}
        return {"error": "No PID provided"}

    async def _handle_plugins_list(self, params: dict) -> dict:
        plugins = [
            {"id": p.manifest.id, "name": p.manifest.name, "version": p.manifest.version}
            for p in self._plugin_loader.loaded_plugins.values()
        ]
        return {"plugins": plugins}

    # --- Subagent RPC Handlers ---

    async def _handle_subagents_list(self, params: dict) -> dict:
        """List all subagent runs."""
        parent_key = params.get("parent_session_key", "")
        if parent_key:
            records = self._subagent_spawner.get_children(parent_key)
        else:
            records = self._subagent_spawner.get_all_records()
        return {
            "subagents": [r.to_dict() for r in records],
            "count": len(records),
        }

    async def _handle_subagents_kill(self, params: dict) -> dict:
        """Kill a running subagent."""
        run_id = params.get("run_id", "")
        if not run_id:
            return {"error": "No run_id provided"}
        killed = await self._subagent_spawner.kill(run_id)
        return {"killed": killed, "run_id": run_id}

    async def _handle_subagents_wait(self, params: dict) -> dict:
        """Wait for a subagent to complete."""
        run_id = params.get("run_id", "")
        timeout = params.get("timeout", 300)
        if not run_id:
            return {"error": "No run_id provided"}
        record = await self._subagent_spawner.wait(run_id, timeout=timeout)
        if record:
            return record.to_dict()
        return {"error": f"Subagent {run_id} not found"}

    async def _announce_subagent_result(
        self, parent_session_key: str, message: str, run_id: str,
    ) -> None:
        """Announce a subagent's result back to the parent session.

        Injects the result as a new message into the parent's session,
        and broadcasts an event to connected clients.
        """
        # Record in parent's transcript
        transcript = self._session_manager.get_or_create(parent_session_key)
        transcript.add_event("subagent_result", {
            "run_id": run_id,
            "message": message[:2000],
        })

        # Broadcast event to all connected clients
        event = create_event("subagent.completed", {
            "run_id": run_id,
            "parent_session_key": parent_session_key,
            "message": message[:2000],
        })
        for client in self._clients:
            try:
                await client.send(event.to_json())
            except Exception:
                pass

        log.info(f"Announced subagent {run_id} result to parent {parent_session_key}")

    # --- Health HTTP Server ---

    async def _start_health_server(self, host: str, port: int) -> None:
        """Start a plain HTTP server for health check probes (HEAD, GET, TCP)."""

        async def _handle_health_http(reader, writer):
            try:
                data = await asyncio.wait_for(reader.read(4096), timeout=5)
                body = json.dumps({"status": "ok", "service": "predator-gateway"}).encode()
                writer.write(
                    b"HTTP/1.1 200 OK\r\n"
                    b"Content-Type: application/json\r\n"
                    b"Content-Length: " + str(len(body)).encode() + b"\r\n"
                    b"Connection: close\r\n"
                    b"\r\n" + body
                )
                await writer.drain()
            except Exception:
                pass
            finally:
                writer.close()

        self._health_server = await asyncio.start_server(_handle_health_http, host, port)
        log.info(f"Health HTTP server on http://{host}:{port}")

    # --- Server Lifecycle ---

    async def start(
        self,
        host: Optional[str] = None,
        port: Optional[int] = None,
        verbose: bool = False,
    ) -> None:
        """Start the gateway server."""
        setup_logging(verbose=verbose)

        host = host or self._config.gateway.host or DEFAULT_GATEWAY_HOST
        port = port or self._config.gateway.port or DEFAULT_GATEWAY_PORT

        # Initialize components
        log.info("Initializing PREDATOR Gateway...")

        # Load plugins
        self._plugin_loader.discover()
        plugin_api = self._plugin_loader.register_all()

        # Create tool registry
        self._registry = create_default_registry()

        # Register plugin tools
        for tool in plugin_api.tools:
            self._registry.register(tool)

        # Register plugin hooks
        for event, handler, priority in plugin_api.hooks:
            self._hook_runner.register(event, handler, priority=priority)

        # Load bundled security hooks
        from predator.hooks.loader import load_bundled_hooks
        load_bundled_hooks(self._hook_runner)

        # Resolve LLM provider
        self._provider = self._resolve_provider()

        # Start process supervisor
        await self._process_supervisor.start()

        # Activate plugins
        self._plugin_loader.activate_all()

        # Run gateway start hook
        await self._hook_runner.run("gateway_start", {"host": host, "port": port})

        self._started_at = time.time()

        # Start plain HTTP health server (for preview/monitoring probes)
        health_port = port + 1  # e.g. 18790
        await self._start_health_server(host, health_port)

        # Start WebSocket server
        log.info(f"PREDATOR Gateway starting on ws://{host}:{port}")

        self._server = await websockets.serve(
            self._handle_connection,
            host,
            port,
            max_size=10 * 1024 * 1024,  # 10MB max frame
        )

        log.info(
            f"PREDATOR Gateway running on ws://{host}:{port} "
            f"(health: http://{host}:{health_port}, "
            f"{self._registry.count} tools, "
            f"provider={self._provider.provider_type.value})"
        )

        # Keep running
        await self._server.wait_closed()

    async def stop(self) -> None:
        """Stop the gateway server."""
        log.info("Stopping PREDATOR Gateway...")

        await self._hook_runner.run("gateway_stop", {})
        self._plugin_loader.deactivate_all()
        await self._process_supervisor.stop()

        if self._health_server:
            self._health_server.close()
            await self._health_server.wait_closed()

        if self._server:
            self._server.close()
            await self._server.wait_closed()

        log.info("PREDATOR Gateway stopped")
