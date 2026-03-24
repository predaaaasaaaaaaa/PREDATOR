"""Gateway rate limiting — mirrors OpenClaw's auth-rate-limit.ts.

Sliding window rate limiter for gateway RPC calls.
Prevents abuse and ensures fair resource usage.
"""

from __future__ import annotations

import time
from collections import defaultdict
from dataclasses import dataclass, field
from typing import Optional

from predator.utils.logger import get_logger

log = get_logger("gateway.rate_limit")


@dataclass
class RateLimitConfig:
    """Rate limiting configuration."""

    requests_per_minute: int = 60
    requests_per_hour: int = 1000
    burst_limit: int = 10  # Max concurrent requests
    block_duration_seconds: int = 300  # 5 min block after exceeding limits
    whitelist: list[str] = field(default_factory=list)  # IPs to skip


@dataclass
class ClientState:
    """Per-client rate limiting state."""

    timestamps: list[float] = field(default_factory=list)
    blocked_until: float = 0.0
    concurrent: int = 0
    total_requests: int = 0


class RateLimiter:
    """Sliding window rate limiter for gateway connections.

    Tracks per-client request rates and blocks clients that exceed limits.
    """

    def __init__(self, config: Optional[RateLimitConfig] = None) -> None:
        self._config = config or RateLimitConfig()
        self._clients: dict[str, ClientState] = defaultdict(ClientState)

    def check(self, client_id: str) -> tuple[bool, str]:
        """Check if a request from client_id is allowed.

        Returns:
            (allowed, reason) — True if allowed, False with denial reason
        """
        if client_id in self._config.whitelist:
            return True, ""

        state = self._clients[client_id]
        now = time.time()

        # Check if blocked
        if state.blocked_until > now:
            remaining = int(state.blocked_until - now)
            return False, f"blocked for {remaining}s"

        # Check burst (concurrent requests)
        if state.concurrent >= self._config.burst_limit:
            return False, f"burst limit ({self._config.burst_limit} concurrent)"

        # Clean old timestamps
        one_hour_ago = now - 3600
        state.timestamps = [t for t in state.timestamps if t > one_hour_ago]

        # Check per-minute
        one_minute_ago = now - 60
        recent = sum(1 for t in state.timestamps if t > one_minute_ago)
        if recent >= self._config.requests_per_minute:
            state.blocked_until = now + self._config.block_duration_seconds
            log.warning(f"Rate limit exceeded (per-minute) for {client_id}, blocking")
            return False, f"exceeded {self._config.requests_per_minute} req/min"

        # Check per-hour
        if len(state.timestamps) >= self._config.requests_per_hour:
            state.blocked_until = now + self._config.block_duration_seconds
            log.warning(f"Rate limit exceeded (per-hour) for {client_id}, blocking")
            return False, f"exceeded {self._config.requests_per_hour} req/hour"

        # Allowed
        state.timestamps.append(now)
        state.total_requests += 1
        return True, ""

    def acquire(self, client_id: str) -> bool:
        """Acquire a concurrent request slot. Returns False if burst limit hit."""
        state = self._clients[client_id]
        if state.concurrent >= self._config.burst_limit:
            return False
        state.concurrent += 1
        return True

    def release(self, client_id: str) -> None:
        """Release a concurrent request slot."""
        state = self._clients[client_id]
        state.concurrent = max(0, state.concurrent - 1)

    def get_stats(self, client_id: str) -> dict:
        """Get rate limit stats for a client."""
        state = self._clients[client_id]
        now = time.time()
        one_minute_ago = now - 60
        recent = sum(1 for t in state.timestamps if t > one_minute_ago)
        return {
            "client_id": client_id,
            "requests_last_minute": recent,
            "requests_last_hour": len(state.timestamps),
            "total_requests": state.total_requests,
            "concurrent": state.concurrent,
            "blocked": state.blocked_until > now,
            "blocked_remaining": max(0, int(state.blocked_until - now)),
        }

    def reset(self, client_id: str) -> None:
        """Reset rate limit state for a client."""
        self._clients.pop(client_id, None)

    def reset_all(self) -> None:
        """Reset all client states."""
        self._clients.clear()
