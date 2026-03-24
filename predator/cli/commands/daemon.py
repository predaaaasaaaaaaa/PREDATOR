"""Daemon command — run PREDATOR as a full autonomous service.

Starts all subsystems: gateway, channels, cron, heartbeat.
This is how you run PREDATOR in production — as an always-on agent.
"""

from __future__ import annotations

import asyncio

import click

from predator.cli.theme import console, print_banner, print_header, print_error, print_success


@click.group("daemon")
def daemon_group():
    """Run PREDATOR as an autonomous daemon (gateway + channels + cron + heartbeat)."""
    pass


@daemon_group.command("run")
@click.option("--no-gateway", is_flag=True, help="Disable WebSocket gateway")
@click.option("--no-channels", is_flag=True, help="Disable chat channel integrations")
@click.option("--no-cron", is_flag=True, help="Disable cron scheduler")
@click.option("--no-heartbeat", is_flag=True, help="Disable heartbeat monitor")
@click.option("--verbose", "-v", is_flag=True, help="Verbose output")
def daemon_run(no_gateway, no_channels, no_cron, no_heartbeat, verbose):
    """Start the full PREDATOR daemon.

    This runs all subsystems together:
    - Gateway (WebSocket RPC for CLI/UI clients)
    - Channels (Telegram, Discord, WhatsApp, Slack, IRC)
    - Cron (scheduled reconnaissance tasks)
    - Heartbeat (periodic monitoring)

    \b
    Examples:
      predator daemon run                  Start everything
      predator daemon run --no-channels    Gateway + cron + heartbeat only
      predator daemon run --no-heartbeat   Skip heartbeat monitoring
    """
    from predator.config.loader import load_config
    from predator.services.orchestrator import Orchestrator

    if verbose:
        from predator.utils.logger import setup_logging
        setup_logging(verbose=True)

    config = load_config()
    print_banner()
    console.print()
    print_header("PREDATOR Daemon Starting")

    services = []
    if not no_gateway:
        services.append("gateway")
    if not no_channels:
        services.append("channels")
    if not no_cron:
        services.append("cron")
    if not no_heartbeat:
        services.append("heartbeat")

    console.print(f"  Services: [info]{', '.join(services)}[/info]")
    console.print()

    async def _run():
        orch = Orchestrator(config)
        await orch.start(
            enable_gateway=not no_gateway,
            enable_channels=not no_channels,
            enable_cron=not no_cron,
            enable_heartbeat=not no_heartbeat,
        )
        print_success("All services running. Press Ctrl+C to stop.")
        try:
            await orch.wait()
        finally:
            await orch.stop()

    try:
        asyncio.run(_run())
    except KeyboardInterrupt:
        console.print("\n[yellow]Daemon shutting down...[/yellow]")


@daemon_group.command("status")
def daemon_status():
    """Check daemon status (gateway + channels)."""
    import asyncio

    async def _check():
        from predator.gateway.client import call_gateway

        try:
            result = await call_gateway("health", timeout=5)
            print_success("PREDATOR daemon is running")
            console.print(f"  Uptime: {result.get('uptime', 0)}s")
            console.print(f"  Provider: {result.get('provider', 'none')}")
            console.print(f"  Tools: {result.get('tools_count', 0)}")
            console.print(f"  Clients: {result.get('clients', 0)}")
        except Exception:
            print_error("Daemon is not running")
            console.print("  [dim]Start with: predator daemon run[/dim]")

    asyncio.run(_check())
