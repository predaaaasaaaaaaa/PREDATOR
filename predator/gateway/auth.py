"""Gateway authentication — mirrors OpenClaw's gateway auth system.

Supports token, password, and device-key authentication.
"""

from __future__ import annotations

from typing import Optional

from predator.utils.crypto import constant_time_compare, generate_token
from predator.utils.logger import get_logger

log = get_logger("gateway.auth")


class GatewayAuth:
    """Handles gateway authentication.

    Mirrors OpenClaw's multi-method auth:
    - Token-based (shared secret)
    - Password-based
    - Device key (Ed25519 PKI)
    """

    def __init__(
        self,
        token: Optional[str] = None,
        password: Optional[str] = None,
    ) -> None:
        self._token = token
        self._password = password
        self._device_keys: dict[str, bytes] = {}  # device_id -> public_key

    def authenticate_token(self, token: str) -> bool:
        if not self._token:
            return True  # No token configured = open
        return constant_time_compare(token, self._token)

    def authenticate_password(self, password: str) -> bool:
        if not self._password:
            return True
        return constant_time_compare(password, self._password)

    def register_device(self, device_id: str, public_key: bytes) -> None:
        self._device_keys[device_id] = public_key
        log.info(f"Registered device: {device_id}")

    def is_device_registered(self, device_id: str) -> bool:
        return device_id in self._device_keys

    @property
    def is_secured(self) -> bool:
        return bool(self._token or self._password)
