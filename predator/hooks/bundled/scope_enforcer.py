"""Scope enforcer hook — ensures tool arguments stay within allowed targets.

Event: ``tool:before`` (runs before tool execution).

The hook inspects tool arguments for IP addresses and domain names and
verifies they fall inside an explicitly configured scope.  If an
out-of-scope target is detected the hook sets ``blocked=True`` and
provides a ``block_reason``.

Scope configuration
-------------------
Pass scope as a dict to the constructor::

    scope = {
        "cidrs": ["10.0.0.0/8", "192.168.1.0/24"],
        "domains": ["example.com", "*.target.org"],
    }
    hook = ScopeEnforcerHook(scope=scope)

* **cidrs** — list of CIDR strings.  An IP is in-scope if it belongs to
  any listed network.
* **domains** — list of domain patterns.  A leading ``*`` acts as a
  wildcard for any subdomain (e.g. ``*.example.com`` matches
  ``sub.example.com``).
"""

from __future__ import annotations

import ipaddress
import re
from typing import Any, Optional

from predator.utils.logger import get_logger

log = get_logger("hooks.bundled.scope_enforcer")

# Regex helpers for extracting IPs and domains from free-form text
_IP_RE = re.compile(
    r"\b(?:\d{1,3}\.){3}\d{1,3}(?:/\d{1,2})?\b"
)
_DOMAIN_RE = re.compile(
    r"\b(?:[a-zA-Z0-9](?:[a-zA-Z0-9-]{0,61}[a-zA-Z0-9])?\.)+[a-zA-Z]{2,}\b"
)


class ScopeEnforcerHook:
    """Blocks tool calls that reference targets outside the configured scope."""

    EVENT = "tool:before"
    PRIORITY = 15  # High priority, right after safety guard
    NAME = "builtin:scope-enforcer"

    def __init__(self, scope: Optional[dict[str, Any]] = None) -> None:
        scope = scope or {}
        # Parse CIDRs into network objects
        self._networks: list[ipaddress.IPv4Network | ipaddress.IPv6Network] = []
        for cidr in scope.get("cidrs", []):
            try:
                self._networks.append(ipaddress.ip_network(cidr, strict=False))
            except ValueError as exc:
                log.warning("Invalid CIDR in scope config '%s': %s", cidr, exc)

        # Normalise domain patterns
        self._domain_patterns: list[str] = [
            d.lower() for d in scope.get("domains", [])
        ]

    # ------------------------------------------------------------------ #
    # Internal helpers
    # ------------------------------------------------------------------ #

    def _ip_in_scope(self, ip_str: str) -> bool:
        """Return ``True`` if *ip_str* belongs to any configured network."""
        if not self._networks:
            return True  # No CIDR scope configured — allow everything
        try:
            addr = ipaddress.ip_address(ip_str.split("/")[0])
        except ValueError:
            return True  # Not a valid IP — skip check
        return any(addr in net for net in self._networks)

    def _domain_in_scope(self, domain: str) -> bool:
        """Return ``True`` if *domain* matches any configured domain pattern."""
        if not self._domain_patterns:
            return True  # No domain scope configured — allow everything
        domain = domain.lower()
        for pattern in self._domain_patterns:
            if pattern.startswith("*."):
                suffix = pattern[1:]  # e.g. ".target.org"
                if domain == pattern[2:] or domain.endswith(suffix):
                    return True
            else:
                if domain == pattern:
                    return True
        return False

    def _extract_and_check(self, text: str) -> Optional[str]:
        """Scan *text* for IPs/domains and return reason if any are out of scope."""
        # Check IPs
        for match in _IP_RE.finditer(text):
            ip_str = match.group()
            if not self._ip_in_scope(ip_str):
                return f"IP {ip_str} is outside configured scope"

        # Check domains
        for match in _DOMAIN_RE.finditer(text):
            domain = match.group()
            if not self._domain_in_scope(domain):
                return f"Domain {domain} is outside configured scope"

        return None

    # ------------------------------------------------------------------ #
    # Hook entry point
    # ------------------------------------------------------------------ #

    async def __call__(self, data: dict[str, Any]) -> Optional[dict[str, Any]]:
        args = data.get("args", data.get("arguments", data.get("command", "")))

        # Flatten to text for scanning
        if isinstance(args, dict):
            text = " ".join(str(v) for v in args.values())
        elif isinstance(args, (list, tuple)):
            text = " ".join(str(v) for v in args)
        else:
            text = str(args)

        reason = self._extract_and_check(text)
        if reason:
            log.warning(
                "ScopeEnforcer BLOCKED tool=%s reason=%s",
                data.get("tool", data.get("tool_name", "unknown")),
                reason,
            )
            data["blocked"] = True
            data["block_reason"] = reason

        return data
