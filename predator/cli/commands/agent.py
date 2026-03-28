"""Agent command — mirrors OpenClaw's agent CLI for sending messages."""
from __future__ import annotations

import asyncio
import sys

import click

from predator.cli.theme import (
    console, print_banner, print_header, print_error, print_info,
    print_tool_start, print_tool_end, print_stats, print_agent_response,
)


@click.command("agent")
@click.option("-m", "--message", default=None, help="Message to send to the agent")
@click.option("--session-id", default="main", help="Session ID (default: main)")
@click.option("--agent-id", default="default", help="Agent ID")
@click.option("--model", default=None, help="Override model")
@click.option("--thinking", type=click.Choice(["off", "low", "high"]), default="low",
              help="Thinking level")
@click.option("--local", is_flag=True, help="Run agent locally (no gateway)")
@click.option("--json-output", "json_out", is_flag=True, help="Output as JSON")
@click.option("--no-stream", is_flag=True, help="Disable streaming output")
@click.argument("trailing_message", nargs=-1)
@click.pass_context
def agent_cmd(ctx, message, session_id, agent_id, model, thinking, local, json_out, no_stream, trailing_message):
    """Send a message to the PREDATOR agent.

    \b
    Examples:
      predator agent -m "Run nmap on 10.0.0.1"
      predator agent -m "Find subdomains for example.com"
      predator agent "What CVEs affect Apache 2.4.49?"
      predator agent scan this target for me
    """
    # Accept message from -m option OR as trailing positional arguments
    if not message and trailing_message:
        message = " ".join(trailing_message)
    elif not message:
        print_error("No message provided. Use: predator agent -m \"your message\" or predator agent your message")
        sys.exit(1)
    if local:
        asyncio.run(_run_local(
            message=message, session_id=session_id, agent_id=agent_id,
            model_override=model, thinking=thinking, json_out=json_out,
        ))
    else:
        asyncio.run(_run_via_gateway(
            message=message, session_id=session_id, agent_id=agent_id,
            json_out=json_out,
        ))


async def _run_local(
    message: str, session_id: str, agent_id: str,
    model_override: str | None, thinking: str, json_out: bool,
):
    """Run agent locally (embedded mode)."""
    from predator.agents.runtime import AgentRuntime
    from predator.config.loader import load_config
    from predator.hooks.runner import HookRunner
    from predator.providers.anthropic import AnthropicProvider
    from predator.providers.openai import OpenAIProvider
    from predator.providers.ollama import OllamaProvider
    from predator.sessions.transcript import SessionTranscript
    from predator.tools.registry import create_default_registry

    config = load_config()

    if model_override:
        config.agent.model = model_override

    thinking_map = {"off": 0, "low": 4096, "high": 16384}
    config.agent.thinking_budget = thinking_map.get(thinking, 4096)

    default_provider = config.providers.default
    if default_provider == "openai":
        provider = OpenAIProvider()
    elif default_provider == "ollama":
        provider = OllamaProvider()
    else:
        provider = AnthropicProvider(default_model=config.agent.model)

    if not provider.is_configured():
        print_error("No LLM provider configured. Run 'predator setup' first.")
        sys.exit(1)

    registry = create_default_registry()
    transcript = SessionTranscript(session_id, agent_id)
    history = transcript.get_message_history()

    output_parts: list[str] = []

    def on_text(text: str):
        if not json_out:
            print_agent_response(text)
        output_parts.append(text)

    def on_thinking(text: str):
        if not json_out:
            console.print(f"[dim]{text}[/dim]", end="")

    def on_tool_start(tool_id: str, name: str, args: dict):
        if not json_out:
            preview = str(args)[:120] if args else ""
            print_tool_start(name, preview)

    def on_tool_end(tool_id: str, name: str, is_error: bool):
        if not json_out:
            print_tool_end(name, is_error)

    runtime = AgentRuntime(
        provider=provider, registry=registry, config=config,
        transcript=transcript, on_text=on_text, on_thinking=on_thinking,
        on_tool_start=on_tool_start, on_tool_end=on_tool_end,
    )

    if not json_out:
        console.print(f"[predator]PREDATOR[/predator] [dim]({config.agent.model})[/dim]\n")

    result = await runtime.run(message=message, history=history, session_id=session_id)

    if json_out:
        import json
        console.print_json(json.dumps({
            "text": result.final_text,
            "turns": len(result.turns),
            "tokens": result.total_tokens,
            "elapsed": round(result.total_elapsed, 2),
            "stopped_reason": result.stopped_reason,
        }))
    else:
        console.print()
        print_stats(len(result.turns), result.total_tokens, result.total_elapsed, result.stopped_reason)


async def _run_via_gateway(message: str, session_id: str, agent_id: str, json_out: bool):
    """Run agent via the gateway."""
    from predator.gateway.client import call_gateway

    try:
        result = await call_gateway(
            method="agent",
            params={"message": message, "session_id": session_id, "agent_id": agent_id},
        )

        if json_out:
            import json
            console.print_json(json.dumps(result))
        else:
            print_agent_response(result.get("text", ""))
            print_stats(
                result.get("turns", 0), result.get("total_tokens", 0),
                result.get("elapsed", 0),
            )
    except Exception as e:
        print_error(f"Gateway error: {e}")
        print_info("Is the gateway running? Start it with: predator gateway run")
        sys.exit(1)
