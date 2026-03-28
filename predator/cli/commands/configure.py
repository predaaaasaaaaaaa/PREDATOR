"""Configure command — interactive setup wizard for ALL PREDATOR settings.

Mirrors OpenClaw's `openclaw configure` command:
- Select a section → interactive prompts → auto-save
- Channel setup: select channel → enter token → done (auto-connects)
- Provider setup: select provider → enter API key → verify → done
- Gateway setup: port, bind mode, auth
- Agent defaults: model, temperature, thinking budget
- Security: exec policy, scan rate, authorization
- OSINT: API keys for Shodan, Hunter, VirusTotal, Censys

Everything is saved to ~/.predator/config.yaml automatically.
"""

from __future__ import annotations

import os
from pathlib import Path
from typing import Optional

import click
from rich.panel import Panel
from rich.prompt import Confirm, IntPrompt, Prompt
from rich.table import Table

from predator.cli.theme import (
    SHARK_SMALL,
    console,
    print_error,
    print_info,
    print_separator,
    print_success,
    print_warning,
)
from predator.config.loader import load_config, write_config
from predator.config.paths import ensure_state_dirs, get_config_path
from predator.config.schema import (
    AuthProfile,
    PredatorConfig,
)
from predator.version import __version__

# ─── PREDATOR Theme Constants ─────────────────────────────────────────
RED = "#FF0033"
GREEN = "#00FF41"
CYAN = "#00D4FF"
AMBER = "#FFB300"
DIM = "#666666"


# ─── Arrow-key interactive selection ─────────────────────────────────
def _select_prompt(message: str, choices: list[dict], default: str | None = None) -> str | None:
    """Arrow-key selection menu using InquirerPy, with Rich fallback."""
    try:
        from InquirerPy import inquirer
        from InquirerPy.base.control import Choice

        inq_choices = [
            Choice(value=c["value"], name=c["name"])
            for c in choices
        ]

        result = inquirer.select(
            message=message,
            choices=inq_choices,
            default=default,
            pointer=">>",
            qmark="",
            amark="",
            instruction="(arrow keys to navigate, Enter to select)",
        ).execute()
        return result
    except (ImportError, Exception):
        # Fallback to numeric selection
        console.print(f"\n[bold {RED}]{message}[/]")
        for i, c in enumerate(choices, 1):
            console.print(f"  [{CYAN}]{i}.[/] {c['name']}")
        selection = Prompt.ask("Enter number", default="1")
        try:
            idx = int(selection) - 1
            if 0 <= idx < len(choices):
                return choices[idx]["value"]
        except (ValueError, IndexError):
            pass
        return choices[0]["value"] if choices else None


def _confirm_prompt(message: str, default: bool = True) -> bool:
    """Confirmation prompt using InquirerPy, with Rich fallback."""
    try:
        from InquirerPy import inquirer
        return inquirer.confirm(
            message=message,
            default=default,
            qmark="",
            amark="",
        ).execute()
    except (ImportError, Exception):
        return Confirm.ask(f"  {message}", default=default)


def _text_prompt(message: str, default: str = "", password: bool = False) -> str:
    """Text input prompt using InquirerPy, with Rich fallback."""
    try:
        from InquirerPy import inquirer
        if password:
            return inquirer.secret(
                message=message,
                default=default,
                qmark="",
                amark="",
            ).execute()
        return inquirer.text(
            message=message,
            default=default,
            qmark="",
            amark="",
        ).execute()
    except (ImportError, Exception):
        return Prompt.ask(f"  {message}", default=default, password=password)


# ─── Channel onboarding instructions ──────────────────────────────────

CHANNEL_INSTRUCTIONS: dict[str, dict] = {
    "telegram": {
        "name": "Telegram",
        "steps": [
            "1. Open Telegram and message @BotFather",
            "2. Send /newbot and follow the prompts",
            "3. Copy the bot token (looks like: 123456:ABC-DEF1234ghIkl-zyx57W2v1u123ew11)",
            "4. Paste it below",
        ],
        "token_prompt": "Telegram bot token",
        "token_hint": "123456:ABC-DEF...",
        "extra_prompts": [
            {
                "key": "allowed_users",
                "prompt": "Allowed Telegram usernames (comma-separated, or * for all)",
                "hint": "your_username, friend_name",
                "type": "list",
            },
        ],
    },
    "discord": {
        "name": "Discord",
        "steps": [
            "1. Go to https://discord.com/developers/applications",
            "2. Click 'New Application' → name it → go to 'Bot' tab",
            "3. Click 'Reset Token' → copy the token",
            "4. Enable 'Message Content Intent' under Privileged Intents",
            "5. Go to OAuth2 → URL Generator → select 'bot' → select permissions",
            "6. Use the generated URL to invite the bot to your server",
            "7. Paste the bot token below",
        ],
        "token_prompt": "Discord bot token",
        "token_hint": "MTIzNDU2Nzg5MDEyMzQ1Njc4.Gg...",
        "extra_prompts": [
            {
                "key": "allowed_guilds",
                "prompt": "Allowed Discord server/guild IDs (comma-separated, or * for all)",
                "hint": "123456789012345678",
                "type": "list",
            },
        ],
    },
    "slack": {
        "name": "Slack",
        "steps": [
            "1. Go to https://api.slack.com/apps → Create New App",
            "2. Choose 'From an app manifest' or configure manually",
            "3. Add Bot Token Scopes: chat:write, channels:history, channels:read",
            "4. Install to Workspace → copy the Bot User OAuth Token (xoxb-...)",
            "5. Enable Socket Mode → copy the App-Level Token (xapp-...)",
            "6. Paste both tokens below",
        ],
        "token_prompt": "Slack bot token (xoxb-...)",
        "token_hint": "xoxb-1234-5678-abcdef",
        "extra_prompts": [
            {
                "key": "app_token",
                "prompt": "Slack app token (xapp-...)",
                "hint": "xapp-1-A1234-1234567890-abcdef",
                "type": "text",
            },
            {
                "key": "allowed_channels",
                "prompt": "Allowed Slack channels (comma-separated, or * for all)",
                "hint": "general, security-ops",
                "type": "list",
            },
        ],
    },
    "whatsapp": {
        "name": "WhatsApp",
        "steps": [
            "1. Set up WhatsApp Business API (Meta Business Suite)",
            "2. Create a WhatsApp Business Account and App",
            "3. Get your API URL and API key from the dashboard",
            "4. Note your WhatsApp phone number",
            "5. Paste the details below",
        ],
        "token_prompt": "WhatsApp API key",
        "token_hint": "your-api-key",
        "extra_prompts": [
            {
                "key": "api_url",
                "prompt": "WhatsApp API URL",
                "hint": "https://graph.facebook.com/v17.0/...",
                "type": "text",
            },
            {
                "key": "phone_number",
                "prompt": "WhatsApp phone number (with country code)",
                "hint": "+1234567890",
                "type": "text",
            },
        ],
    },
    "irc": {
        "name": "IRC",
        "steps": [
            "1. Choose an IRC server (e.g., irc.libera.chat)",
            "2. Decide on a nickname and channels to join",
            "3. Enter the details below",
        ],
        "token_prompt": "IRC server hostname",
        "token_hint": "irc.libera.chat",
        "extra_prompts": [
            {
                "key": "port",
                "prompt": "IRC port",
                "hint": "6697",
                "type": "int",
                "default": 6697,
            },
            {
                "key": "nick",
                "prompt": "Bot nickname",
                "hint": "PREDATOR",
                "type": "text",
                "default": "PREDATOR",
            },
            {
                "key": "channels",
                "prompt": "Channels to join (comma-separated)",
                "hint": "#security, #pentesting",
                "type": "list",
            },
            {
                "key": "ssl",
                "prompt": "Use SSL?",
                "type": "confirm",
                "default": True,
            },
        ],
    },
    "signal": {
        "name": "Signal",
        "steps": [
            "1. Install signal-cli: https://github.com/AsamK/signal-cli",
            "2. Register a phone number with signal-cli",
            "3. Start signal-cli in JSON-RPC daemon mode:",
            "   signal-cli -u +YOURNUMBER daemon --json-rpc",
            "4. Enter your phone number below",
        ],
        "token_prompt": "Signal phone number (with +country code)",
        "token_hint": "+1234567890",
        "extra_prompts": [
            {
                "key": "signal_cli_url",
                "prompt": "signal-cli JSON-RPC URL",
                "hint": "http://localhost:7583/api/v1/rpc",
                "type": "text",
                "default": "http://localhost:7583/api/v1/rpc",
            },
            {
                "key": "allowed_contacts",
                "prompt": "Allowed contacts (phone numbers, comma-separated, or * for all)",
                "hint": "+1234567890, +0987654321",
                "type": "list",
            },
        ],
    },
    "matrix": {
        "name": "Matrix",
        "steps": [
            "1. Create a Matrix account on your homeserver",
            "2. Get an access token (Settings → Help & About → Access Token)",
            "3. Or use the Matrix SDK to login and get a token",
            "4. Enter the details below",
        ],
        "token_prompt": "Matrix access token",
        "token_hint": "syt_...",
        "extra_prompts": [
            {
                "key": "homeserver_url",
                "prompt": "Matrix homeserver URL",
                "hint": "https://matrix.org",
                "type": "text",
            },
            {
                "key": "user_id",
                "prompt": "Matrix user ID",
                "hint": "@predator:matrix.org",
                "type": "text",
            },
            {
                "key": "allowed_rooms",
                "prompt": "Allowed room IDs (comma-separated, or * for all)",
                "hint": "!abc123:matrix.org",
                "type": "list",
            },
        ],
    },
}


# ─── Section handlers ─────────────────────────────────────────────────

def _configure_channels(config: PredatorConfig) -> PredatorConfig:
    """Interactive channel configuration — mirrors OpenClaw's onboard-channels.ts."""
    console.print()
    console.print(Panel(
        f"[bold {RED}]>>> Channel Configuration[/]\n"
        f"[{CYAN}]Connect PREDATOR to chat platforms so you can control it remotely.[/]",
        border_style=RED,
        title=f"[bold {RED}]PREDATOR[/]",
        title_align="left",
    ))
    console.print()

    while True:
        # Show current channel status
        table = Table(title=f"[bold {RED}]Chat Channels[/]", show_header=True, border_style=DIM)
        table.add_column("Channel", style=f"bold {CYAN}")
        table.add_column("Status", style="dim")
        table.add_column("Details", style="dim")

        channel_status = {
            "telegram": ("configured" if config.channels.telegram.token else "not configured",
                         f"Token: ...{config.channels.telegram.token[-8:]}" if config.channels.telegram.token else ""),
            "discord": ("configured" if config.channels.discord.token else "not configured",
                        f"Token: ...{config.channels.discord.token[-8:]}" if config.channels.discord.token else ""),
            "slack": ("configured" if config.channels.slack.bot_token else "not configured",
                      f"Bot: ...{config.channels.slack.bot_token[-8:]}" if config.channels.slack.bot_token else ""),
            "whatsapp": ("configured" if config.channels.whatsapp.api_key else "not configured",
                         f"Phone: {config.channels.whatsapp.phone_number}" if config.channels.whatsapp.phone_number else ""),
            "irc": ("configured" if config.channels.irc.server else "not configured",
                    f"{config.channels.irc.server}:{config.channels.irc.port}" if config.channels.irc.server else ""),
            "signal": ("configured" if config.channels.signal.phone_number else "not configured",
                       f"Phone: {config.channels.signal.phone_number}" if config.channels.signal.phone_number else ""),
            "matrix": ("configured" if config.channels.matrix.access_token else "not configured",
                       f"User: {config.channels.matrix.user_id}" if config.channels.matrix.user_id else ""),
        }

        for ch_name, (status, details) in channel_status.items():
            status_style = f"[{GREEN}]configured[/]" if status == "configured" else f"[{AMBER}]not configured[/]"
            table.add_row(ch_name.capitalize(), status_style, details)

        console.print(table)
        console.print()

        # Channel selection with arrow keys
        menu_choices = []
        for ch_key in CHANNEL_INSTRUCTIONS:
            label = CHANNEL_INSTRUCTIONS[ch_key]["name"]
            status = channel_status.get(ch_key, ("not configured", ""))[0]
            marker = " (configured)" if status == "configured" else ""
            menu_choices.append({"value": ch_key, "name": f"{label}{marker}"})
        menu_choices.append({"value": "done", "name": "Done — finish configuration"})

        selection = _select_prompt("Select a channel to configure:", menu_choices, default="done")

        if selection == "done" or selection is None:
            break

        channel_key = selection

        # Configure the selected channel
        config = _onboard_channel(config, channel_key)
        console.print()

    return config


def _onboard_channel(config: PredatorConfig, channel_key: str) -> PredatorConfig:
    """Onboard a single channel — show instructions, collect credentials, save."""
    info = CHANNEL_INSTRUCTIONS[channel_key]

    console.print()
    steps_text = "\n".join(f"[{CYAN}]{s}[/]" for s in info["steps"])
    console.print(Panel(
        f"[bold {RED}]>>> {info['name']} Setup[/]\n\n{steps_text}",
        border_style=RED,
        title=f"[bold {RED}]PREDATOR[/]",
        title_align="left",
    ))
    console.print()

    # Collect main token/credential
    token = Prompt.ask(
        f"  {info['token_prompt']}",
        default="",
    )

    if not token:
        print_warning(f"Skipped {info['name']} setup")
        return config

    # Collect extra prompts
    extras: dict = {}
    for ep in info.get("extra_prompts", []):
        if ep["type"] == "text":
            value = Prompt.ask(f"  {ep['prompt']}", default=ep.get("default", ""))
            if value:
                extras[ep["key"]] = value
        elif ep["type"] == "int":
            value = IntPrompt.ask(f"  {ep['prompt']}", default=ep.get("default", 0))
            extras[ep["key"]] = value
        elif ep["type"] == "list":
            value = Prompt.ask(f"  {ep['prompt']}", default="")
            if value:
                extras[ep["key"]] = [v.strip() for v in value.split(",") if v.strip()]
        elif ep["type"] == "confirm":
            value = Confirm.ask(f"  {ep['prompt']}", default=ep.get("default", True))
            extras[ep["key"]] = value

    # Apply to config
    if channel_key == "telegram":
        config.channels.telegram.token = token
        if "allowed_users" in extras:
            config.channels.telegram.allowed_users = extras["allowed_users"]

    elif channel_key == "discord":
        config.channels.discord.token = token
        if "allowed_guilds" in extras:
            config.channels.discord.allowed_guilds = extras["allowed_guilds"]

    elif channel_key == "slack":
        config.channels.slack.bot_token = token
        if "app_token" in extras:
            config.channels.slack.app_token = extras["app_token"]
        if "allowed_channels" in extras:
            config.channels.slack.allowed_channels = extras["allowed_channels"]

    elif channel_key == "whatsapp":
        config.channels.whatsapp.api_key = token
        if "api_url" in extras:
            config.channels.whatsapp.api_url = extras["api_url"]
        if "phone_number" in extras:
            config.channels.whatsapp.phone_number = extras["phone_number"]

    elif channel_key == "irc":
        config.channels.irc.server = token
        for k in ("port", "nick", "channels", "ssl"):
            if k in extras:
                setattr(config.channels.irc, k, extras[k])

    elif channel_key == "signal":
        config.channels.signal.phone_number = token
        if "signal_cli_url" in extras:
            config.channels.signal.signal_cli_url = extras["signal_cli_url"]
        if "allowed_contacts" in extras:
            config.channels.signal.allowed_contacts = extras["allowed_contacts"]

    elif channel_key == "matrix":
        config.channels.matrix.access_token = token
        for k in ("homeserver_url", "user_id", "allowed_rooms"):
            if k in extras:
                setattr(config.channels.matrix, k, extras[k])

    # Save immediately
    write_config(config)
    print_success(f"{info['name']} configured and saved!")

    # Show how to start
    console.print(f"\n  [{DIM}]To start with {info['name']}:[/] [bold #FF0033]predator gateway start --channels {channel_key}[/]")

    return config


def _configure_providers(config: PredatorConfig) -> PredatorConfig:
    """Interactive LLM provider configuration."""
    console.print()
    console.print(Panel(
        f"[bold {RED}]>>> LLM Provider Configuration[/]\n"
        f"[{CYAN}]Set up API keys for the AI models that power PREDATOR.[/]",
        border_style=RED,
        title=f"[bold {RED}]PREDATOR[/]",
        title_align="left",
    ))
    console.print()

    providers = [
        ("anthropic", "Anthropic (Claude)", "ANTHROPIC_API_KEY", "sk-ant-..."),
        ("openai", "OpenAI (GPT)", "OPENAI_API_KEY", "sk-..."),
        ("openrouter", "OpenRouter (multi-model)", "OPENROUTER_API_KEY", "sk-or-..."),
    ]

    for provider_id, name, env_var, hint in providers:
        existing = config.providers.profiles.get(provider_id)
        env_key = os.environ.get(env_var, "")

        status = ""
        if existing and existing.api_key:
            status = f" [{GREEN}](configured: ...{existing.api_key[-8:]})[/]"
        elif env_key:
            status = f" [{GREEN}](from env: ...{env_key[-8:]})[/]"
        else:
            status = f" [{AMBER}](not configured)[/]"

        if Confirm.ask(f"  Configure {name}?{status}", default=not bool(existing and existing.api_key or env_key)):
            key = Prompt.ask(f"    API key ({hint})", default="")
            if key:
                config.providers.profiles[provider_id] = AuthProfile(
                    provider=provider_id, api_key=key
                )
                write_config(config)
                print_success(f"{name} configured!")
            else:
                if env_key:
                    print_info(f"Using {env_var} from environment")
                else:
                    print_warning(f"Skipped — set {env_var} env var or run configure again")

    # Default provider — arrow key selection
    console.print()
    current_default = config.providers.default
    provider_choices = [
        {"value": "anthropic", "name": "Anthropic (Claude)"},
        {"value": "openai", "name": "OpenAI (GPT)"},
        {"value": "openrouter", "name": "OpenRouter (multi-model)"},
        {"value": "ollama", "name": "Ollama (local LLM)"},
    ]
    new_default = _select_prompt("Default LLM provider:", provider_choices, default=current_default)
    if new_default and new_default != current_default:
        config.providers.default = new_default
        write_config(config)
        print_success(f"Default provider set to {new_default}")

    # Ollama (local)
    if Confirm.ask("  Configure Ollama (local LLM)?", default=False):
        base_url = Prompt.ask("    Ollama base URL", default="http://localhost:11434")
        model = Prompt.ask("    Ollama model name", default="llama3.1")
        config.providers.profiles["ollama"] = AuthProfile(
            provider="ollama", base_url=base_url, model=model
        )
        write_config(config)
        print_success("Ollama configured!")

    return config


def _configure_agent(config: PredatorConfig) -> PredatorConfig:
    """Interactive agent defaults configuration."""
    console.print()
    console.print(Panel(
        f"[bold {RED}]>>> Agent Defaults[/]\n"
        f"[{CYAN}]Configure the AI agent's behavior.[/]",
        border_style=RED,
        title=f"[bold {RED}]PREDATOR[/]",
        title_align="left",
    ))
    console.print()

    # Model
    model = Prompt.ask(
        f"  Model [{config.agent.model}]",
        default=config.agent.model,
    )
    config.agent.model = model

    # Temperature
    temp = Prompt.ask(
        f"  Temperature (0.0-1.0) [{config.agent.temperature}]",
        default=str(config.agent.temperature),
    )
    try:
        config.agent.temperature = float(temp)
    except ValueError:
        pass

    # Max tokens
    tokens = Prompt.ask(
        f"  Max tokens [{config.agent.max_tokens}]",
        default=str(config.agent.max_tokens),
    )
    try:
        config.agent.max_tokens = int(tokens)
    except ValueError:
        pass

    # Thinking budget
    thinking = Prompt.ask(
        f"  Thinking budget [{config.agent.thinking_budget}]",
        default=str(config.agent.thinking_budget),
    )
    try:
        config.agent.thinking_budget = int(thinking)
    except ValueError:
        pass

    write_config(config)
    print_success("Agent defaults saved!")
    return config


def _configure_gateway(config: PredatorConfig) -> PredatorConfig:
    """Interactive gateway configuration."""
    console.print()
    console.print(Panel(
        f"[bold {RED}]>>> Gateway Configuration[/]\n"
        f"[{CYAN}]Configure the WebSocket gateway server.[/]",
        border_style=RED,
        title=f"[bold {RED}]PREDATOR[/]",
        title_align="left",
    ))
    console.print()

    port = IntPrompt.ask(f"  Port [{config.gateway.port}]", default=config.gateway.port)
    config.gateway.port = port

    bind = Prompt.ask(
        f"  Bind mode [{config.gateway.bind_mode}]",
        choices=["loopback", "lan", "custom"],
        default=config.gateway.bind_mode,
    )
    config.gateway.bind_mode = bind

    if bind == "lan":
        config.gateway.host = "0.0.0.0"
    elif bind == "custom":
        host = Prompt.ask("  Custom bind address", default=config.gateway.host)
        config.gateway.host = host
    else:
        config.gateway.host = "localhost"

    # Auth
    if Confirm.ask("  Set gateway password?", default=bool(config.gateway.password)):
        password = Prompt.ask("  Gateway password", password=True)
        config.gateway.password = password

    # TLS
    if Confirm.ask("  Enable TLS?", default=bool(config.gateway.tls_cert)):
        cert = Prompt.ask("  TLS certificate path", default=config.gateway.tls_cert or "")
        key = Prompt.ask("  TLS key path", default=config.gateway.tls_key or "")
        if cert and key:
            config.gateway.tls_cert = cert
            config.gateway.tls_key = key

    write_config(config)
    print_success("Gateway configuration saved!")
    return config


def _configure_osint(config: PredatorConfig) -> PredatorConfig:
    """Interactive OSINT API keys configuration."""
    console.print()
    console.print(Panel(
        f"[bold {RED}]>>> OSINT API Keys[/]\n"
        f"[{CYAN}]Optional API keys for enhanced OSINT capabilities.[/]",
        border_style=RED,
        title=f"[bold {RED}]PREDATOR[/]",
        title_align="left",
    ))
    console.print()

    api_keys = [
        ("shodan_api_key", "Shodan API key", "Get from: https://account.shodan.io"),
        ("hunter_api_key", "Hunter.io API key", "Get from: https://hunter.io/api-keys"),
        ("virustotal_api_key", "VirusTotal API key", "Get from: https://www.virustotal.com/gui/my-apikey"),
        ("censys_api_id", "Censys API ID", "Get from: https://search.censys.io/account/api"),
        ("censys_api_secret", "Censys API Secret", ""),
    ]

    for attr, label, help_text in api_keys:
        current = getattr(config.osint, attr, None)
        status = f" [{GREEN}](set)[/]" if current else ""
        if help_text:
            console.print(f"  [dim]{help_text}[/dim]")
        value = Prompt.ask(f"  {label}{status}", default=current or "")
        if value:
            setattr(config.osint, attr, value)

    # Passive only mode
    config.osint.passive_only = not Confirm.ask(
        "  Allow active scanning?", default=not config.osint.passive_only
    )

    write_config(config)
    print_success("OSINT configuration saved!")
    return config


def _configure_security(config: PredatorConfig) -> PredatorConfig:
    """Interactive security policy configuration."""
    console.print()
    console.print(Panel(
        f"[bold {RED}]>>> Security Policy[/]\n"
        f"[{CYAN}]Configure execution security and safety controls.[/]",
        border_style=RED,
        title=f"[bold {RED}]PREDATOR[/]",
        title_align="left",
    ))
    console.print()

    # Exec security mode
    mode = Prompt.ask(
        f"  Exec security mode [{config.exec.security_mode}]",
        choices=["deny", "allowlist", "full"],
        default=config.exec.security_mode,
    )
    config.exec.security_mode = mode

    if mode == "full":
        print_warning("'full' mode allows ALL commands without approval — use with caution!")

    # Exec timeout
    timeout = IntPrompt.ask(
        f"  Command timeout (seconds) [{config.exec.timeout}]",
        default=config.exec.timeout,
    )
    config.exec.timeout = timeout

    # Authorization required
    config.security.require_authorization = Confirm.ask(
        "  Require authorization for active scanning?",
        default=config.security.require_authorization,
    )

    write_config(config)
    print_success("Security policy saved!")
    return config


def _configure_identity(config: PredatorConfig) -> PredatorConfig:
    """Interactive identity configuration."""
    console.print()
    console.print(Panel(
        f"[bold {RED}]>>> Bot Identity[/]\n"
        f"[{CYAN}]Customize PREDATOR's name and description.[/]",
        border_style=RED,
        title=f"[bold {RED}]PREDATOR[/]",
        title_align="left",
    ))
    console.print()

    name = Prompt.ask(f"  Bot name [{config.identity.name}]", default=config.identity.name)
    config.identity.name = name

    desc = Prompt.ask(
        f"  Description [{config.identity.description}]",
        default=config.identity.description,
    )
    config.identity.description = desc

    extra = Prompt.ask(
        "  Extra system prompt (additional instructions, or Enter to skip)",
        default=config.identity.system_prompt_extra or "",
    )
    if extra:
        config.identity.system_prompt_extra = extra

    write_config(config)
    print_success("Identity saved!")
    return config


# ─── Main configure command ───────────────────────────────────────────

SECTIONS = {
    "channels": ("Chat Channels", "Connect Telegram, Discord, Slack, WhatsApp, IRC, Signal, Matrix", _configure_channels),
    "providers": ("LLM Providers", "Set up API keys for Claude, GPT, Ollama, OpenRouter", _configure_providers),
    "agent": ("Agent Defaults", "Model, temperature, thinking budget", _configure_agent),
    "gateway": ("Gateway", "WebSocket server, port, auth, TLS", _configure_gateway),
    "osint": ("OSINT API Keys", "Shodan, Hunter.io, VirusTotal, Censys", _configure_osint),
    "security": ("Security Policy", "Exec mode, timeouts, authorization", _configure_security),
    "identity": ("Identity", "Bot name, description, extra prompt", _configure_identity),
}


@click.command("configure")
@click.argument("section", required=False)
def configure_cmd(section: Optional[str] = None):
    """Interactive configuration wizard — set up channels, providers, and more.

    \b
    Usage:
      predator configure            Full interactive wizard
      predator configure channels   Just channel setup
      predator configure providers  Just LLM provider setup
      predator configure gateway    Just gateway setup
      predator configure osint      Just OSINT API keys
      predator configure security   Just security policy
      predator configure identity   Just bot identity
      predator configure agent      Just agent defaults
    """
    console.print()
    console.print(SHARK_SMALL)
    console.print(Panel(
        f"[bold {RED}]PREDATOR[/] [{DIM}]// Configure[/]\n"
        f"[{DIM}]v{__version__}[/]",
        border_style=RED,
    ))
    print_separator()

    # Ensure state dirs exist
    ensure_state_dirs()

    # Load current config
    config = load_config()

    if section:
        # Direct section
        if section not in SECTIONS:
            print_error(f"Unknown section: {section}")
            console.print(f"Available: {', '.join(SECTIONS.keys())}")
            return
        _, _, handler = SECTIONS[section]
        config = handler(config)
    else:
        # Full interactive wizard — arrow key menu
        while True:
            console.print()

            section_list = list(SECTIONS.items())
            menu_choices = [
                {"value": key, "name": f"{name} — {desc}"}
                for key, (name, desc, _) in section_list
            ]
            menu_choices.append({"value": "done", "name": "Done — exit configure"})

            choice = _select_prompt("What would you like to configure?", menu_choices, default="done")

            if choice == "done" or choice is None:
                break

            if choice in SECTIONS:
                _, _, handler = SECTIONS[choice]
                config = handler(config)

    console.print()
    console.print(Panel(
        f"[bold {RED}]Configuration complete![/]\n\n"
        f"[{DIM}]Config saved to:[/] [{DIM}]{get_config_path()}[/]\n\n"
        f"[bold {RED}]Quick start:[/]\n"
        f"  [dim #CC0029]$[/] [bold #FF0033]predator gateway start[/]                        [{DIM}]Start the gateway[/]\n"
        f"  [dim #CC0029]$[/] [bold #FF0033]predator gateway start --channels telegram[/]     [{DIM}]Start with Telegram[/]\n"
        f"  [dim #CC0029]$[/] [bold #FF0033]predator gateway start --channels all[/]          [{DIM}]Start all channels[/]\n"
        f"  [dim #CC0029]$[/] [bold #FF0033]predator agent -m \"...\"[/]                       [{DIM}]Talk to the agent[/]\n"
        f"  [dim #CC0029]$[/] [bold #FF0033]predator daemon run[/]                            [{DIM}]Full autonomous mode[/]",
        border_style=RED,
        title=f"[bold {RED}]PREDATOR[/]",
        title_align="left",
    ))
