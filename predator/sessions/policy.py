"""Session send policy — mirrors OpenClaw's sessions/send-policy.ts.

Controls message routing and session isolation rules.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Optional


@dataclass
class PolicyRule:
    """A single policy rule for message routing."""

    session_prefix: Optional[str] = None
    action: str = "allow"  # allow | deny
    reason: str = ""


class SendPolicy:
    """Message send policy engine.

    Mirrors OpenClaw's policy evaluation:
    - Default allow/deny
    - Rule-based matching on session keys
    - Per-session overrides
    """

    def __init__(self, default_action: str = "allow") -> None:
        self._default = default_action
        self._rules: list[PolicyRule] = []

    def add_rule(self, rule: PolicyRule) -> None:
        self._rules.append(rule)

    def evaluate(self, session_id: str) -> tuple[str, str]:
        """Evaluate the policy for a session.

        Returns (action, reason).
        """
        for rule in self._rules:
            if rule.session_prefix and session_id.startswith(rule.session_prefix):
                return rule.action, rule.reason

        return self._default, "default policy"
