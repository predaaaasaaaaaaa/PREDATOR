"""Gateway CLI commands — mirrors OpenClaw's gateway-cli/ module."""

from __future__ import annotations

import asyncio

import click

from predator.cli.theme import console, print_header, print_success, print_error, print_warning, print_info


@click.group("gateway")
def gateway_group():
    """Manage the PREDATOR Gateway (WebSocket control plane)."""
    pass


@gateway_group.command("run")
@click.option("--host", default=None, help="Bind host (default: 127.0.0.1)")
@click.option("--port", "-p", default=None, type=int, help="Bind port (default: 18789)")
@click.option("--verbose", "-v", is_flag=True, help="Verbose output")
def gateway_run(host, port, verbose):
    """Start the PREDATOR Gateway server.

    The gateway is the WebSocket control plane that manages agent sessions,
    tool execution, and plugin lifecycle.
    """
    from predator.config.loader import load_config
    from predator.gateway.server import GatewayServer

    config = load_config()
    server = GatewayServer(config)

    console.print("[bold red]Starting PREDATOR Gateway...[/bold red]")

    try:
        asyncio.run(server.start(host=host, port=port, verbose=verbose))
    except KeyboardInterrupt:
        print_warning("Gateway shutting down...")
        asyncio.run(server.stop())


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
