"""Default configuration values — mirrors OpenClaw's config/defaults.ts."""

from __future__ import annotations

# Agent defaults
DEFAULT_MODEL = "claude-sonnet-4-20250514"
DEFAULT_TEMPERATURE = 0.7
DEFAULT_MAX_TOKENS = 8192
DEFAULT_THINKING_BUDGET = 4096

# Gateway defaults
DEFAULT_GATEWAY_PORT = 18789
DEFAULT_GATEWAY_HOST = "127.0.0.1"
DEFAULT_GATEWAY_BIND = "loopback"

# Process execution defaults
DEFAULT_EXEC_TIMEOUT = 1800  # 30 minutes
DEFAULT_OUTPUT_LIMIT = 204800  # 200KB
DEFAULT_NO_OUTPUT_TIMEOUT = 300  # 5 minutes

# Session defaults
DEFAULT_HISTORY_LENGTH = 50
DEFAULT_COMPACTION_THRESHOLD = 40

# Memory defaults
DEFAULT_MAX_MEMORY_RESULTS = 10
DEFAULT_SNIPPET_MAX_CHARS = 700
DEFAULT_MEMORY_BACKEND = "builtin"

# Security defaults
DEFAULT_SECURITY_MODE = "allowlist"
DEFAULT_ASK_MODE = "on-miss"

# OSINT defaults
DEFAULT_OSINT_TIMEOUT = 600  # 10 minutes for long-running OSINT tools
DEFAULT_SCAN_RATE = 1000  # packets per second for scanners

# Rate limiting
DEFAULT_RATE_LIMIT_RPM = 60  # requests per minute
DEFAULT_RATE_LIMIT_TPM = 100000  # tokens per minute
