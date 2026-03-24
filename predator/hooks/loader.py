"""Hook loader — registers bundled and workspace hooks with a HookRunner.

Public API
----------
* :func:`load_bundled_hooks` — registers the three built-in security /
  observability hooks.
* :func:`load_workspace_hooks` — discovers ``.hook.py`` / ``.hook.sh``
  files in a workspace directory and registers them.
"""

from __future__ import annotations

import importlib.util
import os
import sys
from pathlib import Path
from typing import Any, Optional

from predator.hooks.bundled.audit_logger import AuditLoggerHook
from predator.hooks.bundled.safety_guard import SafetyGuardHook
from predator.hooks.bundled.scope_enforcer import ScopeEnforcerHook
from predator.hooks.frontmatter import discover_hooks
from predator.hooks.runner import HookRunner
from predator.utils.logger import get_logger

log = get_logger("hooks.loader")


# ---------------------------------------------------------------------- #
# Bundled hooks
# ---------------------------------------------------------------------- #

def load_bundled_hooks(
    runner: HookRunner,
    *,
    scope: Optional[dict[str, Any]] = None,
    audit_path: Optional[str | Path] = None,
) -> None:
    """Register all bundled hooks on *runner*.

    Parameters
    ----------
    runner:
        The :class:`HookRunner` instance to register hooks on.
    scope:
        Optional scope config forwarded to :class:`ScopeEnforcerHook`.
    audit_path:
        Optional override for the audit log file location.
    """
    safety = SafetyGuardHook()
    runner.register(
        event=safety.EVENT,
        handler=safety,
        source="builtin",
        priority=safety.PRIORITY,
        name=safety.NAME,
    )

    enforcer = ScopeEnforcerHook(scope=scope)
    runner.register(
        event=enforcer.EVENT,
        handler=enforcer,
        source="builtin",
        priority=enforcer.PRIORITY,
        name=enforcer.NAME,
    )

    audit = AuditLoggerHook(audit_path=audit_path)
    runner.register(
        event=audit.EVENT,
        handler=audit,
        source="builtin",
        priority=audit.PRIORITY,
        name=audit.NAME,
    )

    log.info("Loaded %d bundled hooks", 3)


# ---------------------------------------------------------------------- #
# Workspace hooks
# ---------------------------------------------------------------------- #

def _load_hook_module(path: str) -> Any:
    """Dynamically import a ``.hook.py`` file and return the module."""
    module_name = Path(path).stem.replace(".", "_")
    spec = importlib.util.spec_from_file_location(module_name, path)
    if spec is None or spec.loader is None:
        log.warning("Cannot create module spec for %s", path)
        return None

    module = importlib.util.module_from_spec(spec)
    sys.modules[module_name] = module
    try:
        spec.loader.exec_module(module)  # type: ignore[union-attr]
    except Exception as exc:
        log.error("Failed to load hook module %s: %s", path, exc)
        del sys.modules[module_name]
        return None
    return module


def load_workspace_hooks(runner: HookRunner, workspace_dir: str) -> None:
    """Discover and register hooks from ``.hook.py`` files in *workspace_dir*.

    Each hook file should contain YAML frontmatter with at least an ``event``
    key, and expose either a callable ``hook`` attribute or a class whose
    name ends with ``Hook`` that can be instantiated with no arguments.
    """
    hooks_dir = os.path.join(workspace_dir, ".predator", "hooks")
    if not os.path.isdir(hooks_dir):
        log.debug("No workspace hooks directory at %s", hooks_dir)
        return

    entries = discover_hooks(hooks_dir)
    loaded = 0

    for meta in entries:
        hook_path: str = meta["path"]
        event: str = meta.get("event", "")
        if not event:
            log.warning("Hook at %s has no 'event' in frontmatter — skipping", hook_path)
            continue

        enabled = meta.get("enabled", True)
        if not enabled:
            log.debug("Hook at %s is disabled — skipping", hook_path)
            continue

        # Only Python hooks can be auto-loaded
        if not hook_path.endswith(".hook.py"):
            log.debug("Skipping non-Python hook %s", hook_path)
            continue

        module = _load_hook_module(hook_path)
        if module is None:
            continue

        # Find callable handler: prefer a `hook` attribute, then any *Hook class
        handler = getattr(module, "hook", None)
        if handler is None:
            for attr_name in dir(module):
                if attr_name.endswith("Hook"):
                    cls = getattr(module, attr_name)
                    if callable(cls):
                        try:
                            handler = cls()
                        except Exception as exc:
                            log.error("Cannot instantiate %s from %s: %s", attr_name, hook_path, exc)
                        break

        if handler is None or not callable(handler):
            log.warning("No callable handler found in %s — skipping", hook_path)
            continue

        priority = meta.get("priority", 100)
        name = meta.get("name", Path(hook_path).stem)

        runner.register(
            event=event,
            handler=handler,
            source="workspace",
            priority=priority,
            name=name,
        )
        loaded += 1

    log.info("Loaded %d workspace hook(s) from %s", loaded, hooks_dir)
