"""Hook runner — mirrors OpenClaw's hook-runner-global.ts.

Executes registered hooks in priority order.
"""

from __future__ import annotations

from typing import Any, Optional

from predator.hooks.types import HookEvent, HookHandler, HookRegistration
from predator.utils.logger import get_logger

log = get_logger("hooks.runner")


class HookRunner:
    """Runs registered hooks for lifecycle events.

    Mirrors OpenClaw's global hook runner:
    - Priority-based execution ordering
    - Async hook handlers
    - Error isolation (one failing hook doesn't break others)
    - Hook result chaining
    """

    def __init__(self) -> None:
        self._hooks: dict[str, list[HookRegistration]] = {}

    def register(
        self,
        event: str | HookEvent,
        handler: HookHandler,
        source: str = "config",
        priority: int = 100,
        name: str = "",
    ) -> None:
        """Register a hook handler for an event."""
        event_key = event.value if isinstance(event, HookEvent) else event
        if event_key not in self._hooks:
            self._hooks[event_key] = []

        self._hooks[event_key].append(
            HookRegistration(
                event=HookEvent(event_key) if event_key in HookEvent.__members__.values() else HookEvent.AGENT_START,
                handler=handler,
                source=source,
                priority=priority,
                name=name,
            )
        )
        # Sort by priority
        self._hooks[event_key].sort(key=lambda h: h.priority)

    async def run(
        self,
        event: str | HookEvent,
        data: dict[str, Any],
    ) -> Optional[dict[str, Any]]:
        """Run all hooks registered for an event.

        Hooks are executed in priority order. Each hook can modify
        the data dict, which is passed to the next hook.
        """
        event_key = event.value if isinstance(event, HookEvent) else event
        hooks = self._hooks.get(event_key, [])

        if not hooks:
            return data

        result = data
        for hook in hooks:
            try:
                hook_result = await hook.handler(result)
                if hook_result is not None:
                    result = hook_result
            except Exception as e:
                log.error(
                    f"Hook '{hook.name or hook.source}' for event '{event_key}' "
                    f"failed: {e}"
                )
                # Continue with other hooks — don't let one failure break the chain

        return result

    def unregister(self, event: str | HookEvent, source: str) -> int:
        """Unregister all hooks from a source for an event."""
        event_key = event.value if isinstance(event, HookEvent) else event
        hooks = self._hooks.get(event_key, [])
        original = len(hooks)
        self._hooks[event_key] = [h for h in hooks if h.source != source]
        return original - len(self._hooks[event_key])

    def list_hooks(self) -> dict[str, list[str]]:
        """List all registered hooks by event."""
        return {
            event: [f"{h.name or h.source} (priority={h.priority})" for h in hooks]
            for event, hooks in self._hooks.items()
        }
