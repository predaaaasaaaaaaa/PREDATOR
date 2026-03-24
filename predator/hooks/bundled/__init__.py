"""Bundled security and observability hooks shipped with PREDATOR."""

from predator.hooks.bundled.audit_logger import AuditLoggerHook
from predator.hooks.bundled.safety_guard import SafetyGuardHook
from predator.hooks.bundled.scope_enforcer import ScopeEnforcerHook

__all__ = [
    "AuditLoggerHook",
    "SafetyGuardHook",
    "ScopeEnforcerHook",
]
