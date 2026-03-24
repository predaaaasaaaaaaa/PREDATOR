"""Channels CLI — manage chat channel integrations."""
from __future__ import annotations

import click

from predator.cli.theme import (
    console, print_banner, print_header, print_success, print_error,
    print_warning, print_info, print_separator,
)


@click.group("channels")
def channels_group():
    """Manage chat channel integrations (Telegram, Discord, WhatsApp, etc.)."""
    pass


@channels_group.command("list")
@click.pass_context
def channels_list(ctx):
    """List all available and configured channels."""
    from predator.channels.registry import create_default_registry
    from predator.config.loader import load_config

    print_header("Chat Channels")
    registry = create_default_registry()
    config = load_config()

    for plugin in registry.list_channels():
        configured = plugin.is_configured(config)
        status = "[success]configured[/success]" if configured else "[dim]not configured[/dim]"
        console.print(f"  [tool.name]{plugin.id:<12}[/tool.name] {plugin.meta.label:<12} {status}")
        if plugin.meta.blurb:
            console.print(f"               [dim]{plugin.meta.blurb}[/dim]")

        # Show accounts if configured
        account_ids = plugin.list_account_ids(config)
        for aid in account_ids:
            snap = plugin.get_account_snapshot(aid, config)
            state = "[success]active[/success]" if snap.connected else "[dim]inactive[/dim]"
            console.print(f"               account: [info]{aid}[/info] {state}")

    console.print()
    print_info("Run 'predator setup' to configure channels")


@channels_group.command("status")
@click.argument("channel_id", required=False)
@click.pass_context
def channels_status(ctx, channel_id):
    """Show channel connection status."""
    from predator.channels.registry import create_default_registry
    from predator.config.loader import load_config

    registry = create_default_registry()
    config = load_config()

    if channel_id:
        plugin = registry.get(channel_id)
        if not plugin:
            print_error(f"Unknown channel: {channel_id}")
            return
        channels = [plugin]
    else:
        channels = registry.list_channels()

    print_header("Channel Status")
    for plugin in channels:
        account_ids = plugin.list_account_ids(config) or ["default"]
        for aid in account_ids:
            snap = plugin.get_account_snapshot(aid, config)
            if snap.connected:
                print_success(f"{plugin.id}/{aid}: connected")
            elif snap.configured:
                print_warning(f"{plugin.id}/{aid}: configured but not running")
            else:
                console.print(f"  [dim]{plugin.id}/{aid}: not configured[/dim]")
            if snap.last_error:
                print_error(f"  Last error: {snap.last_error}")


@channels_group.command("test")
@click.argument("channel_id")
@click.argument("to")
@click.option("-m", "--message", default="PREDATOR test message", help="Test message")
@click.pass_context
def channels_test(ctx, channel_id, to, message):
    """Send a test message through a channel."""
    import asyncio
    from predator.channels.registry import create_default_registry
    from predator.config.loader import load_config

    registry = create_default_registry()
    config = load_config()

    plugin = registry.get(channel_id)
    if not plugin:
        print_error(f"Unknown channel: {channel_id}")
        return

    if not plugin.is_configured(config):
        print_error(f"Channel {channel_id} is not configured")
        return

    async def send_test():
        try:
            result = await plugin.send_text(to=to, text=message)
            print_success(f"Message sent via {channel_id} (ID: {result.message_id})")
        except Exception as e:
            print_error(f"Send failed: {e}")

    asyncio.run(send_test())
