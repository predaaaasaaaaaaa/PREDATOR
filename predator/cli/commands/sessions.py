"""Sessions CLI commands — mirrors OpenClaw's session management."""

from __future__ import annotations

import click
from rich.table import Table

from predator.cli.theme import console, print_header, print_success, print_error, print_warning, print_info


@click.group("sessions")
def sessions_group():
    """Manage agent sessions."""
    pass


@sessions_group.command("list")
@click.option("--agent-id", default="default", help="Agent ID")
def sessions_list(agent_id):
    """List all sessions."""
    from predator.sessions.transcript import SessionManager

    manager = SessionManager(agent_id)
    sessions = manager.list_sessions()

    if sessions:
        table = Table(title="Sessions")
        table.add_column("Session ID", style="bold")

        for session_id in sorted(sessions):
            table.add_row(session_id)

        console.print(table)
    else:
        console.print("[dim]No sessions found[/dim]")


@sessions_group.command("delete")
@click.argument("session_id")
@click.option("--agent-id", default="default")
@click.confirmation_option(prompt="Delete this session?")
def sessions_delete(session_id, agent_id):
    """Delete a session."""
    from predator.sessions.transcript import SessionManager

    manager = SessionManager(agent_id)
    if manager.delete_session(session_id):
        print_success(f"Session '{session_id}' deleted")
    else:
        print_error(f"Session '{session_id}' not found")


@sessions_group.command("clear")
@click.option("--agent-id", default="default")
@click.confirmation_option(prompt="Delete ALL sessions?")
def sessions_clear(agent_id):
    """Delete all sessions."""
    from predator.sessions.transcript import SessionManager

    manager = SessionManager(agent_id)
    sessions = manager.list_sessions()
    for sid in sessions:
        manager.delete_session(sid)
    print_success(f"Deleted {len(sessions)} sessions")


@sessions_group.command("new")
@click.option("--agent-id", default="default")
@click.option("--label", "-l", default=None, help="Label for the new session")
def sessions_new(agent_id, label):
    """Start a fresh session (like /new).

    The agent wakes up with full context from SOUL.md, IDENTITY.md,
    USER.md, and MEMORY.md — only the conversation history is reset.
    """
    import uuid

    from predator.sessions.transcript import SessionManager

    manager = SessionManager(agent_id)
    session_id = label or f"session-{uuid.uuid4().hex[:8]}"
    transcript = manager.get_or_create(session_id)

    print_success(f"New session: {session_id}")
    console.print("  [dim]The agent retains its memory via .md files.[/dim]")
    console.print("  [dim]Use: predator agent -m '...' --session " + session_id + "[/dim]")
