"""Gateway CLI commands — mirrors OpenClaw's gateway-cli/ module."""

from __future__ import annotations

import asyncio

import click

from predator.cli.theme import (
    console, print_banner, print_header, print_success, print_error,
    print_warning, print_info,
)


@click.group("gateway")
def gateway_group():
    """Manage the PREDATOR Gateway (WebSocket control plane)."""
    pass


def _run_gateway(host, port, verbose, channels):
    """Shared logic for gateway run/start commands."""
    from predator.config.loader import load_config
    from predator.services.orchestrator import Orchestrator

    config = load_config()

    # Determine which services to enable
    enable_channels = bool(channels)
    channel_filter = None
    if channels:
        channel_filter = [c.strip().lower() for c in channels.split(",")]

    print_banner(compact=True)
    console.print()

    async def _start():
        orch = Orchestrator(config)

        # Apply host/port overrides
        if host:
            config.gateway.host = host
        if port:
            config.gateway.port = port

        await orch.start(
            enable_gateway=True,
            enable_channels=enable_channels,
            enable_cron=False,
            enable_heartbeat=False,
            channel_filter=channel_filter,
        )

        gw_host = host or config.gateway.host or "127.0.0.1"
        gw_port = port or config.gateway.port or 18789

        print_success(f"Gateway running on ws://{gw_host}:{gw_port}")
        print_success(f"Health endpoint: http://{gw_host}:{gw_port + 1}")

        if enable_channels:
            active = orch._channel_service.active_channels if orch._channel_service else []
            if active:
                for ch_id, acc_id in active:
                    print_success(f"Channel active: {ch_id}/{acc_id}")
            else:
                print_warning("No channels started (check config: predator configure channels)")
        else:
            print_info("Channels disabled. Use --channels to enable (e.g. --channels telegram)")

        console.print()
        print_info("Press Ctrl+C to stop")

        try:
            await orch.wait()
        finally:
            await orch.stop()

    try:
        asyncio.run(_start())
    except KeyboardInterrupt:
        print_warning("Gateway shutting down...")


@gateway_group.command("run")
@click.option("--host", default=None, help="Bind host (default: 127.0.0.1)")
@click.option("--port", "-p", default=None, type=int, help="Bind port (default: 18789)")
@click.option("--verbose", "-v", is_flag=True, help="Verbose output")
@click.option("--channels", default=None, help="Enable channels (e.g. telegram, discord, or 'all')")
def gateway_run(host, port, verbose, channels):
    """Start the PREDATOR Gateway server.

    \b
    The gateway is the WebSocket control plane that manages agent sessions,
    tool execution, and plugin lifecycle.

    \b
    Examples:
      predator gateway run                          Start gateway only
      predator gateway run --channels telegram      Start with Telegram bot
      predator gateway run --channels all           Start with all configured channels
    """
    _run_gateway(host, port, verbose, channels)


@gateway_group.command("start")
@click.option("--host", default=None, help="Bind host (default: 127.0.0.1)")
@click.option("--port", "-p", default=None, type=int, help="Bind port (default: 18789)")
@click.option("--verbose", "-v", is_flag=True, help="Verbose output")
@click.option("--channels", default=None, help="Enable channels (e.g. telegram, discord, or 'all')")
def gateway_start(host, port, verbose, channels):
    """Start the PREDATOR Gateway server (alias for 'run').

    \b
    Examples:
      predator gateway start                          Start gateway only
      predator gateway start --channels telegram      Start with Telegram bot
      predator gateway start --channels all           Start with all configured channels
    """
    _run_gateway(host, port, verbose, channels)


@gateway_group.command("status")
@click.option("--host", default="127.0.0.1")
@click.option("--port", "-p", default=18789, type=int)
def gateway_status(host, port):
    """Check if the gateway is running and show its status."""

    async def _check():
        from predator.gateway.client import call_gateway

        try:
            result = await call_gateway("health", host=host, port=port, timeout=5)
            print_success("Gateway is running")
            console.print(f"  Version: {result.get('version', 'unknown')}")
            console.print(f"  Uptime: {result.get('uptime', 0)}s")
            console.print(f"  Provider: {result.get('provider', 'none')}")
            console.print(f"  Tools: {result.get('tools_count', 0)}")
            console.print(f"  Clients: {result.get('clients', 0)}")
            console.print(f"  Processes: {result.get('active_processes', 0)}")
        except Exception:
            print_error(f"Gateway is not running on {host}:{port}")
            console.print("[dim]Start it with: predator gateway run[/dim]")

    asyncio.run(_check())


@gateway_group.command("health")
@click.option("--host", default="127.0.0.1")
@click.option("--port", "-p", default=18789, type=int)
def gateway_health(host, port):
    """Fetch detailed gateway health information."""

    async def _check():
        from predator.gateway.client import call_gateway

        try:
            result = await call_gateway("health", host=host, port=port, timeout=5)
            import json
            console.print_json(json.dumps(result))
        except Exception as e:
            print_error(f"Cannot reach gateway: {e}")

    asyncio.run(_check())
