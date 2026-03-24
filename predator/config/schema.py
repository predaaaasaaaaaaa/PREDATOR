"""Configuration schema — mirrors OpenClaw's config/zod-schema.ts using Pydantic.

Defines the full PREDATOR configuration structure with validation.
"""

from __future__ import annotations

from typing import Any, Optional

from pydantic import BaseModel, Field

from predator.config.defaults import (
    DEFAULT_ASK_MODE,
    DEFAULT_COMPACTION_THRESHOLD,
    DEFAULT_EXEC_TIMEOUT,
    DEFAULT_GATEWAY_BIND,
    DEFAULT_GATEWAY_HOST,
    DEFAULT_GATEWAY_PORT,
    DEFAULT_HISTORY_LENGTH,
    DEFAULT_MAX_TOKENS,
    DEFAULT_MEMORY_BACKEND,
    DEFAULT_MODEL,
    DEFAULT_NO_OUTPUT_TIMEOUT,
    DEFAULT_OSINT_TIMEOUT,
    DEFAULT_OUTPUT_LIMIT,
    DEFAULT_RATE_LIMIT_RPM,
    DEFAULT_RATE_LIMIT_TPM,
    DEFAULT_SCAN_RATE,
    DEFAULT_SECURITY_MODE,
    DEFAULT_TEMPERATURE,
    DEFAULT_THINKING_BUDGET,
)


# --- Identity ---
class IdentityConfig(BaseModel):
    """Bot identity — mirrors OpenClaw's identity config."""

    name: str = "PREDATOR"
    description: str = "Autonomous AI agent for ethical hacking & cybersecurity"
    avatar: Optional[str] = None
    system_prompt_extra: Optional[str] = None


# --- Provider Auth ---
class AuthProfile(BaseModel):
    """LLM provider authentication profile."""

    provider: str = "anthropic"  # anthropic | openai | ollama | openrouter
    api_key: Optional[str] = None
    base_url: Optional[str] = None
    model: Optional[str] = None
    organization: Optional[str] = None
    cooldown_seconds: int = 0
    max_rpm: int = DEFAULT_RATE_LIMIT_RPM
    max_tpm: int = DEFAULT_RATE_LIMIT_TPM


class ProvidersConfig(BaseModel):
    """LLM provider configuration."""

    default: str = "anthropic"
    profiles: dict[str, AuthProfile] = Field(default_factory=lambda: {
        "anthropic": AuthProfile(provider="anthropic"),
    })


# --- Agent ---
class AgentToolPolicy(BaseModel):
    """Tool allow/block policy for an agent."""

    allowed: list[str] = Field(default_factory=list)
    blocked: list[str] = Field(default_factory=list)


class AgentConfig(BaseModel):
    """Per-agent configuration — mirrors OpenClaw's agents config."""

    model: str = DEFAULT_MODEL
    temperature: float = DEFAULT_TEMPERATURE
    max_tokens: int = DEFAULT_MAX_TOKENS
    thinking_budget: int = DEFAULT_THINKING_BUDGET
    system_prompt: Optional[str] = None
    tools: AgentToolPolicy = Field(default_factory=AgentToolPolicy)
    history_length: int = DEFAULT_HISTORY_LENGTH
    compaction_threshold: int = DEFAULT_COMPACTION_THRESHOLD


# --- Execution ---
class ExecConfig(BaseModel):
    """Process execution configuration — mirrors OpenClaw's exec policies."""

    timeout: int = DEFAULT_EXEC_TIMEOUT
    output_limit: int = DEFAULT_OUTPUT_LIMIT
    no_output_timeout: int = DEFAULT_NO_OUTPUT_TIMEOUT
    security_mode: str = DEFAULT_SECURITY_MODE  # deny | allowlist | full
    ask_mode: str = DEFAULT_ASK_MODE  # off | on-miss | always
    blocked_env_vars: list[str] = Field(default_factory=lambda: [
        "LD_PRELOAD", "LD_LIBRARY_PATH", "PYTHONPATH", "PYTHONHOME",
        "RUBYLIB", "PERL5LIB", "BASH_ENV", "ENV",
    ])
    allowed_commands: list[str] = Field(default_factory=list)
    blocked_commands: list[str] = Field(default_factory=list)


# --- OSINT ---
class OSINTConfig(BaseModel):
    """OSINT-specific configuration."""

    default_timeout: int = DEFAULT_OSINT_TIMEOUT
    scan_rate: int = DEFAULT_SCAN_RATE
    passive_only: bool = False  # Only allow passive recon by default
    require_authorization: bool = True  # Require explicit auth for active scanning
    output_dir: str = "~/predator-reports"
    shodan_api_key: Optional[str] = None
    hunter_api_key: Optional[str] = None
    virustotal_api_key: Optional[str] = None
    censys_api_id: Optional[str] = None
    censys_api_secret: Optional[str] = None


# --- Gateway ---
class GatewayConfig(BaseModel):
    """Gateway (WebSocket control plane) configuration."""

    port: int = DEFAULT_GATEWAY_PORT
    host: str = DEFAULT_GATEWAY_HOST
    bind_mode: str = DEFAULT_GATEWAY_BIND  # loopback | lan | custom
    token: Optional[str] = None
    password: Optional[str] = None
    tls_cert: Optional[str] = None
    tls_key: Optional[str] = None
    max_connections: int = 10
    tick_interval: int = 30


# --- Plugins ---
class PluginEntry(BaseModel):
    """Plugin configuration entry."""

    enabled: bool = True
    path: Optional[str] = None
    config: dict[str, Any] = Field(default_factory=dict)


class PluginsConfig(BaseModel):
    """Plugin system configuration."""

    auto_discover: bool = True
    entries: dict[str, PluginEntry] = Field(default_factory=dict)


# --- Memory ---
class MemoryConfig(BaseModel):
    """Memory/knowledge system configuration."""

    backend: str = DEFAULT_MEMORY_BACKEND  # builtin | custom
    enabled: bool = True
    max_results: int = 10
    max_snippet_chars: int = 700
    retention_days: int = 90
    auto_save: bool = True


# --- Channels ---
class TelegramConfig(BaseModel):
    """Telegram bot configuration."""

    token: Optional[str] = None
    allowed_users: list[str] = Field(default_factory=list)
    polling_timeout: int = 30


class DiscordConfig(BaseModel):
    """Discord bot configuration."""

    token: Optional[str] = None
    allowed_guilds: list[str] = Field(default_factory=list)
    intents: list[str] = Field(default_factory=lambda: [
        "guilds", "guild_messages", "message_content",
    ])


class SlackConfig(BaseModel):
    """Slack app configuration."""

    bot_token: Optional[str] = None
    app_token: Optional[str] = None
    allowed_channels: list[str] = Field(default_factory=list)


class WhatsAppConfig(BaseModel):
    """WhatsApp Business API configuration."""

    api_url: Optional[str] = None
    api_key: Optional[str] = None
    phone_number: Optional[str] = None


class IRCConfig(BaseModel):
    """IRC client configuration."""

    server: Optional[str] = None
    port: int = 6697
    nick: str = "PREDATOR"
    channels: list[str] = Field(default_factory=list)
    ssl: bool = True


class SignalConfig(BaseModel):
    """Signal messenger configuration (via signal-cli JSON-RPC)."""

    signal_cli_url: str = "http://localhost:7583/api/v1/rpc"
    phone_number: Optional[str] = None
    allowed_contacts: list[str] = Field(default_factory=list)


class MatrixConfig(BaseModel):
    """Matrix protocol configuration (via matrix-nio)."""

    homeserver_url: Optional[str] = None
    access_token: Optional[str] = None
    user_id: Optional[str] = None
    allowed_rooms: list[str] = Field(default_factory=list)


class ChannelsConfig(BaseModel):
    """Channel-specific configuration for all supported platforms."""

    telegram: TelegramConfig = Field(default_factory=TelegramConfig)
    discord: DiscordConfig = Field(default_factory=DiscordConfig)
    slack: SlackConfig = Field(default_factory=SlackConfig)
    whatsapp: WhatsAppConfig = Field(default_factory=WhatsAppConfig)
    irc: IRCConfig = Field(default_factory=IRCConfig)
    signal: SignalConfig = Field(default_factory=SignalConfig)
    matrix: MatrixConfig = Field(default_factory=MatrixConfig)


# --- Heartbeat ---
class HeartbeatConfig(BaseModel):
    """Heartbeat / keep-alive configuration for autonomous operation."""

    interval_ms: int = 60000
    model: Optional[str] = None
    target: Optional[str] = None
    to: Optional[str] = None
    active_hours_start: Optional[str] = None  # e.g. "08:00"
    active_hours_end: Optional[str] = None    # e.g. "22:00"
    active_hours_tz: str = "UTC"


# --- Cron ---
class CronConfig(BaseModel):
    """Cron / scheduled-task configuration."""

    state_dir: str = "~/.predator/cron"
    max_concurrent_jobs: int = 4


# --- Security ---
class SecurityConfig(BaseModel):
    """Global security policy settings."""

    require_authorization: bool = True
    audit_log_path: Optional[str] = None
    max_tool_calls_per_minute: int = 60
    blocked_tools: list[str] = Field(default_factory=list)


# --- Hooks ---
class HookEntry(BaseModel):
    """Hook configuration entry."""

    event: str  # e.g., "agent:start", "tool:before", "message:received"
    command: Optional[str] = None
    script: Optional[str] = None
    enabled: bool = True


class HooksConfig(BaseModel):
    """Hook system configuration."""

    entries: list[HookEntry] = Field(default_factory=list)


# --- Root Config ---
class PredatorConfig(BaseModel):
    """Root PREDATOR configuration — mirrors OpenClaw's full config schema.

    Loaded from ~/.predator/config.yaml with env var substitution.
    """

    identity: IdentityConfig = Field(default_factory=IdentityConfig)
    providers: ProvidersConfig = Field(default_factory=ProvidersConfig)
    agent: AgentConfig = Field(default_factory=AgentConfig)
    agents: dict[str, AgentConfig] = Field(default_factory=dict)
    exec: ExecConfig = Field(default_factory=ExecConfig)
    osint: OSINTConfig = Field(default_factory=OSINTConfig)
    gateway: GatewayConfig = Field(default_factory=GatewayConfig)
    plugins: PluginsConfig = Field(default_factory=PluginsConfig)
    memory: MemoryConfig = Field(default_factory=MemoryConfig)
    hooks: HooksConfig = Field(default_factory=HooksConfig)
    channels: ChannelsConfig = Field(default_factory=ChannelsConfig)
    heartbeat: HeartbeatConfig = Field(default_factory=HeartbeatConfig)
    cron: CronConfig = Field(default_factory=CronConfig)
    security: SecurityConfig = Field(default_factory=SecurityConfig)
    workspace_dir: str = "."

    class Config:
        extra = "allow"  # Allow unknown fields for forward-compat
