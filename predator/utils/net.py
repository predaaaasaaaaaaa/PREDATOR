"""Network utilities — mirrors OpenClaw's gateway/net.ts.

Handles IP validation, private network detection, and port management.
"""

from __future__ import annotations

import ipaddress
import socket
from typing import Optional


def is_private_ip(addr: str) -> bool:
    """Check if an IP address is private (RFC1918, link-local, loopback, ULA)."""
    try:
        ip = ipaddress.ip_address(addr)
        return ip.is_private or ip.is_loopback or ip.is_link_local
    except ValueError:
        return False


def is_loopback(addr: str) -> bool:
    """Check if address is loopback."""
    try:
        return ipaddress.ip_address(addr).is_loopback
    except ValueError:
        return addr in ("localhost", "127.0.0.1", "::1")


def get_local_ip() -> str:
    """Get the primary local IP address."""
    try:
        s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        s.connect(("8.8.8.8", 80))
        ip = s.getsockname()[0]
        s.close()
        return ip
    except OSError:
        return "127.0.0.1"


def is_port_available(port: int, host: str = "127.0.0.1") -> bool:
    """Check if a port is available for binding."""
    try:
        s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        s.settimeout(1)
        s.bind((host, port))
        s.close()
        return True
    except OSError:
        return False


def find_available_port(start: int = 18789, end: int = 18889) -> Optional[int]:
    """Find an available port in the given range."""
    for port in range(start, end + 1):
        if is_port_available(port):
            return port
    return None


DEFAULT_GATEWAY_PORT = 18789
DEFAULT_GATEWAY_HOST = "127.0.0.1"
