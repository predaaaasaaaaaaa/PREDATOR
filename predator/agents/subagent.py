"""Subagent orchestration system — mirrors OpenClaw's subagent-spawn.ts.

Full multi-agent orchestration:
- Depth-limited spawning with safety guardrails
- Registry tracking of all active/completed subagents
- Auto-announce: results flow back to parent session automatically
- Steering: parent can redirect a running subagent mid-task
- Kill: parent can terminate a running subagent
- Wait: parent can block until a subagent finishes
- Lifecycle events for gateway integration
"""

from __future__ import annotations

import asyncio
import json
import time
import uuid
from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path
from typing import Any, Callable, Optional

from predator.agents.lanes import CommandLane
from predator.utils.logger import get_logger

log = get_logger("agents.subagent")


# ═══════════════════════════════════════════════════════════════════
# Data structures
# ═══════════════════════════════════════════════════════════════════


class SubagentState(str, Enum):
    PENDING = "pending"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELLED = "cancelled"
    TIMEOUT = "timeout"


@dataclass
class SubagentRunRecord:
    """Tracks a spawned subagent run — mirrors OpenClaw's SubagentRunRecord."""

    run_id: str = ""
    session_key: str = ""
    parent_session_key: str = ""
    agent_id: str = ""
    label: str = ""
    task: str = ""
    model: str = ""
    thinking_level: str = "low"
    lane: CommandLane = CommandLane.SUBAGENT
    state: SubagentState = SubagentState.PENDING
    spawn_depth: int = 0

    # Results
    result_text: str = ""
    error: str = ""
    total_tokens: int = 0
    turns: int = 0

    # Timing
    created_at: float = 0.0
    started_at: float = 0.0
    completed_at: float = 0.0
    timeout_seconds: int = 600

    # Lifecycle
    cleanup: str = "keep"  # "keep" or "delete"
    announced: bool = False
    _task_handle: Optional[asyncio.Task] = field(default=None, repr=False)

    @property
    def elapsed(self) -> float:
        end = self.completed_at or time.time()
        start = self.started_at or self.created_at
        return end - start if start else 0.0

    @property
    def is_done(self) -> bool:
        return self.state in (
            SubagentState.COMPLETED,
            SubagentState.FAILED,
            SubagentState.CANCELLED,
            SubagentState.TIMEOUT,
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "run_id": self.run_id,
            "session_key": self.session_key,
            "parent_session_key": self.parent_session_key,
            "agent_id": self.agent_id,
            "label": self.label,
            "task": self.task[:200],
            "model": self.model,
            "state": self.state.value,
            "spawn_depth": self.spawn_depth,
            "result_text": self.result_text[:500] if self.result_text else "",
            "error": self.error,
            "total_tokens": self.total_tokens,
            "turns": self.turns,
            "elapsed": round(self.elapsed, 2),
            "announced": self.announced,
        }


@dataclass
class SpawnParams:
    """Parameters for spawning a subagent."""

    task: str
    label: str = ""
    agent_id: str = "default"
    model: str = ""
    thinking_level: str = "low"
    timeout_seconds: int = 600
    cleanup: str = "keep"


# ═══════════════════════════════════════════════════════════════════
# Subagent Registry — tracks all spawned subagents
# ═══════════════════════════════════════════════════════════════════


class SubagentRegistry:
    """In-memory registry of all subagent runs.

    Mirrors OpenClaw's subagent-registry.ts:
    - Tracks all active and completed subagent runs
    - Supports parent-child lookups
    - Emits lifecycle events
    - Can persist to disk for cross-process visibility
    """

    def __init__(self, persist_dir: Optional[Path] = None) -> None:
        self._records: dict[str, SubagentRunRecord] = {}
        self._by_parent: dict[str, list[str]] = {}
        self._lifecycle_listeners: list[Callable] = []
        self._persist_dir = persist_dir
        self._completion_events: dict[str, asyncio.Event] = {}

    def register(self, record: SubagentRunRecord) -> None:
        """Register a new subagent run."""
        self._records[record.run_id] = record
        parent = record.parent_session_key
        if parent not in self._by_parent:
            self._by_parent[parent] = []
        self._by_parent[parent].append(record.run_id)
        self._completion_events[record.run_id] = asyncio.Event()
        self._persist()
        log.info(
            f"Registered subagent {record.run_id} "
            f"(parent={parent}, depth={record.spawn_depth})"
        )

    def get(self, run_id: str) -> Optional[SubagentRunRecord]:
        return self._records.get(run_id)

    def get_children(self, parent_session_key: str) -> list[SubagentRunRecord]:
        run_ids = self._by_parent.get(parent_session_key, [])
        return [self._records[rid] for rid in run_ids if rid in self._records]

    def get_active_children(self, parent_session_key: str) -> list[SubagentRunRecord]:
        return [
            r for r in self.get_children(parent_session_key)
            if r.state in (SubagentState.PENDING, SubagentState.RUNNING)
        ]

    def get_active_count(self, parent_session_key: str) -> int:
        return len(self.get_active_children(parent_session_key))

    def update_state(
        self, run_id: str, state: SubagentState, **kwargs: Any,
    ) -> None:
        """Update a subagent's state and trigger lifecycle events."""
        record = self._records.get(run_id)
        if not record:
            return

        old_state = record.state
        record.state = state
        for k, v in kwargs.items():
            if hasattr(record, k):
                setattr(record, k, v)

        # Mark completion event
        if record.is_done:
            event = self._completion_events.get(run_id)
            if event:
                event.set()

        self._persist()
        self._emit_lifecycle(record, old_state)

    async def wait_for_completion(
        self, run_id: str, timeout: float = 600,
    ) -> Optional[SubagentRunRecord]:
        """Wait for a subagent to complete. Returns the record or None on timeout."""
        record = self._records.get(run_id)
        if not record:
            return None
        if record.is_done:
            return record

        event = self._completion_events.get(run_id)
        if not event:
            return None

        try:
            await asyncio.wait_for(event.wait(), timeout=timeout)
            return self._records.get(run_id)
        except asyncio.TimeoutError:
            return self._records.get(run_id)

    def all_records(self) -> list[SubagentRunRecord]:
        return list(self._records.values())

    def cleanup_old(self, max_age_seconds: float = 3600) -> int:
        """Remove completed subagent records older than max_age."""
        now = time.time()
        to_remove = []
        for rid, record in self._records.items():
            if record.is_done and record.cleanup == "delete":
                if record.completed_at and (now - record.completed_at) > max_age_seconds:
                    to_remove.append(rid)

        for rid in to_remove:
            del self._records[rid]
            for parent_runs in self._by_parent.values():
                if rid in parent_runs:
                    parent_runs.remove(rid)
            self._completion_events.pop(rid, None)

        if to_remove:
            self._persist()
            log.info(f"Cleaned up {len(to_remove)} old subagent records")
        return len(to_remove)

    def on_lifecycle(self, listener: Callable) -> None:
        """Register a lifecycle event listener."""
        self._lifecycle_listeners.append(listener)

    def _emit_lifecycle(
        self, record: SubagentRunRecord, old_state: SubagentState,
    ) -> None:
        for listener in self._lifecycle_listeners:
            try:
                listener({
                    "type": "subagent_lifecycle",
                    "run_id": record.run_id,
                    "session_key": record.session_key,
                    "parent_session_key": record.parent_session_key,
                    "old_state": old_state.value,
                    "new_state": record.state.value,
                    "label": record.label,
                })
            except Exception as e:
                log.error(f"Lifecycle listener error: {e}")

    def _persist(self) -> None:
        """Persist registry to disk for cross-process visibility."""
        if not self._persist_dir:
            return
        try:
            self._persist_dir.mkdir(parents=True, exist_ok=True)
            path = self._persist_dir / "subagent-registry.json"
            data = {rid: r.to_dict() for rid, r in self._records.items()}
            path.write_text(json.dumps(data, indent=2))
        except Exception as e:
            log.debug(f"Failed to persist registry: {e}")


# ═══════════════════════════════════════════════════════════════════
# Subagent Depth Tracker
# ═══════════════════════════════════════════════════════════════════


class SubagentDepthTracker:
    """Tracks spawn depth per session — prevents infinite recursion.

    Mirrors OpenClaw's subagent-depth.ts.
    """

    def __init__(self, max_depth: int = 2) -> None:
        self._depths: dict[str, int] = {}
        self._max_depth = max_depth

    def get_depth(self, session_key: str) -> int:
        return self._depths.get(session_key, 0)

    def set_depth(self, session_key: str, depth: int) -> None:
        self._depths[session_key] = depth

    def can_spawn(self, parent_session_key: str) -> tuple[bool, str]:
        depth = self.get_depth(parent_session_key)
        if depth >= self._max_depth:
            return False, f"Max spawn depth reached ({self._max_depth})"
        return True, ""

    def register_child(self, parent_session_key: str, child_session_key: str) -> int:
        parent_depth = self.get_depth(parent_session_key)
        child_depth = parent_depth + 1
        self._depths[child_session_key] = child_depth
        return child_depth

    def remove(self, session_key: str) -> None:
        self._depths.pop(session_key, None)


# ═══════════════════════════════════════════════════════════════════
# Auto-Announce System
# ═══════════════════════════════════════════════════════════════════


class SubagentAnnouncer:
    """Auto-announces subagent results back to the parent session.

    Mirrors OpenClaw's subagent-announce.ts:
    - When a subagent finishes, formats the result
    - Sends it back to the parent session as a new message
    - Supports retry with exponential backoff
    """

    def __init__(
        self,
        registry: SubagentRegistry,
        announce_callback: Optional[Callable] = None,
    ) -> None:
        self._registry = registry
        self._announce_callback = announce_callback
        self._max_retries = 3
        self._retry_delays = [1.0, 2.0, 4.0]

        # Listen for lifecycle events
        registry.on_lifecycle(self._on_lifecycle_event)

    def _on_lifecycle_event(self, event: dict) -> None:
        """Handle subagent lifecycle events."""
        new_state = event.get("new_state")
        if new_state in ("completed", "failed", "timeout", "cancelled"):
            run_id = event.get("run_id", "")
            # Schedule announce in background (safe for any context)
            try:
                loop = asyncio.get_running_loop()
                loop.create_task(self._announce(run_id))
            except RuntimeError:
                # No running loop — skip announce (will be picked up later)
                pass

    async def _announce(self, run_id: str) -> None:
        """Announce subagent result to parent."""
        record = self._registry.get(run_id)
        if not record or record.announced:
            return

        message = self._format_announcement(record)

        for attempt in range(self._max_retries):
            try:
                if self._announce_callback:
                    await self._announce_callback(
                        parent_session_key=record.parent_session_key,
                        message=message,
                        run_id=run_id,
                    )
                record.announced = True
                log.info(
                    f"Announced subagent {run_id} result to "
                    f"parent {record.parent_session_key}"
                )
                return
            except Exception as e:
                if attempt < self._max_retries - 1:
                    delay = self._retry_delays[attempt]
                    log.warning(
                        f"Announce failed for {run_id} (attempt {attempt + 1}), "
                        f"retrying in {delay}s: {e}"
                    )
                    await asyncio.sleep(delay)
                else:
                    log.error(f"Failed to announce subagent {run_id} after {self._max_retries} retries")

    def _format_announcement(self, record: SubagentRunRecord) -> str:
        """Format the announcement message for the parent."""
        if record.state == SubagentState.COMPLETED:
            header = f"[SUBAGENT COMPLETED] {record.label}"
            body = record.result_text or "(no output)"
        elif record.state == SubagentState.FAILED:
            header = f"[SUBAGENT FAILED] {record.label}"
            body = f"Error: {record.error}" if record.error else "(unknown error)"
        elif record.state == SubagentState.TIMEOUT:
            header = f"[SUBAGENT TIMEOUT] {record.label}"
            body = f"Timed out after {record.timeout_seconds}s"
        elif record.state == SubagentState.CANCELLED:
            header = f"[SUBAGENT CANCELLED] {record.label}"
            body = "Cancelled by parent agent"
        else:
            header = f"[SUBAGENT {record.state.value.upper()}] {record.label}"
            body = record.result_text or record.error or ""

        stats = (
            f"Turns: {record.turns} | Tokens: {record.total_tokens} | "
            f"Time: {record.elapsed:.1f}s"
        )

        return f"{header}\nTask: {record.task[:200]}\n\n{body}\n\n[Stats: {stats}]"


# ═══════════════════════════════════════════════════════════════════
# Subagent Spawner — the main orchestrator
# ═══════════════════════════════════════════════════════════════════


class SubagentSpawner:
    """Spawns and manages subagent runs.

    Mirrors OpenClaw's spawnSubagentDirect():
    - Validates depth and children limits
    - Creates isolated session for child
    - Runs child agent asynchronously
    - Tracks lifecycle via registry
    - Auto-announces results to parent
    - Supports steering and killing
    """

    def __init__(
        self,
        registry: Optional[SubagentRegistry] = None,
        depth_tracker: Optional[SubagentDepthTracker] = None,
        announcer: Optional[SubagentAnnouncer] = None,
        max_children: int = 5,
        max_depth: int = 2,
        announce_callback: Optional[Callable] = None,
    ) -> None:
        self._registry = registry or SubagentRegistry()
        self._depth_tracker = depth_tracker or SubagentDepthTracker(max_depth=max_depth)
        self._max_children = max_children
        self._steering_messages: dict[str, list[str]] = {}

        # Set up announcer
        self._announcer = announcer or SubagentAnnouncer(
            registry=self._registry,
            announce_callback=announce_callback,
        )

    @property
    def registry(self) -> SubagentRegistry:
        return self._registry

    def can_spawn(self, parent_session_key: str) -> tuple[bool, str]:
        """Check if spawning is allowed."""
        # Check depth
        ok, reason = self._depth_tracker.can_spawn(parent_session_key)
        if not ok:
            return False, reason

        # Check active children count
        active = self._registry.get_active_count(parent_session_key)
        if active >= self._max_children:
            return False, f"Max concurrent children reached ({self._max_children})"

        return True, ""

    async def spawn(
        self,
        params: SpawnParams,
        parent_session_key: str,
        runtime_factory: Optional[Callable] = None,
    ) -> SubagentRunRecord:
        """Spawn a new subagent. Returns immediately (async execution)."""
        can, reason = self.can_spawn(parent_session_key)
        if not can:
            record = SubagentRunRecord(
                run_id=uuid.uuid4().hex[:12],
                parent_session_key=parent_session_key,
                task=params.task,
                label=params.label or "subagent",
                state=SubagentState.FAILED,
                error=f"Spawn forbidden: {reason}",
                created_at=time.time(),
                completed_at=time.time(),
            )
            self._registry.register(record)
            return record

        run_id = uuid.uuid4().hex[:12]
        session_key = f"agent:{params.agent_id}:subagent:{run_id}"

        child_depth = self._depth_tracker.register_child(
            parent_session_key, session_key
        )

        record = SubagentRunRecord(
            run_id=run_id,
            session_key=session_key,
            parent_session_key=parent_session_key,
            agent_id=params.agent_id,
            label=params.label or f"subagent-{run_id[:6]}",
            task=params.task,
            model=params.model,
            thinking_level=params.thinking_level,
            lane=CommandLane.SUBAGENT,
            state=SubagentState.PENDING,
            spawn_depth=child_depth,
            created_at=time.time(),
            timeout_seconds=params.timeout_seconds,
            cleanup=params.cleanup,
        )
        self._registry.register(record)

        # Launch the subagent in the background
        task = asyncio.create_task(
            self._run_subagent(record, params, runtime_factory)
        )
        record._task_handle = task

        log.info(
            f"Spawned subagent {run_id} (label={record.label}, "
            f"depth={child_depth}, parent={parent_session_key})"
        )
        return record

    async def _run_subagent(
        self,
        record: SubagentRunRecord,
        params: SpawnParams,
        runtime_factory: Optional[Callable],
    ) -> None:
        """Execute a subagent in an isolated session."""
        try:
            self._registry.update_state(
                record.run_id, SubagentState.RUNNING,
                started_at=time.time(),
            )

            # Create the runtime
            runtime = await self._create_runtime(record, params, runtime_factory)

            # Run with timeout
            result = await asyncio.wait_for(
                runtime.run(
                    message=params.task,
                    session_id=record.session_key,
                ),
                timeout=params.timeout_seconds,
            )

            self._registry.update_state(
                record.run_id,
                SubagentState.COMPLETED,
                result_text=result.final_text,
                total_tokens=result.total_tokens,
                turns=len(result.turns),
                completed_at=time.time(),
            )
            log.info(
                f"Subagent {record.run_id} completed: "
                f"{len(result.turns)} turns, {result.total_tokens} tokens"
            )

        except asyncio.TimeoutError:
            self._registry.update_state(
                record.run_id, SubagentState.TIMEOUT,
                error=f"Timeout after {params.timeout_seconds}s",
                completed_at=time.time(),
            )
            log.warning(f"Subagent {record.run_id} timed out")

        except asyncio.CancelledError:
            self._registry.update_state(
                record.run_id, SubagentState.CANCELLED,
                error="Cancelled by parent",
                completed_at=time.time(),
            )
            log.info(f"Subagent {record.run_id} cancelled")

        except Exception as e:
            self._registry.update_state(
                record.run_id, SubagentState.FAILED,
                error=str(e),
                completed_at=time.time(),
            )
            log.error(f"Subagent {record.run_id} failed: {e}")

        finally:
            self._depth_tracker.remove(record.session_key)

    async def _create_runtime(
        self,
        record: SubagentRunRecord,
        params: SpawnParams,
        runtime_factory: Optional[Callable],
    ) -> Any:
        """Create an AgentRuntime for the subagent."""
        if runtime_factory:
            return runtime_factory(record)

        from predator.agents.runtime import AgentRuntime
        from predator.config.loader import load_config
        from predator.hooks.runner import HookRunner
        from predator.providers.anthropic import AnthropicProvider
        from predator.providers.ollama import OllamaProvider
        from predator.providers.openai import OpenAIProvider
        from predator.sessions.transcript import SessionTranscript
        from predator.tools.registry import create_default_registry

        config = load_config()

        # Apply model override
        if params.model:
            config.agent.model = params.model

        # Apply thinking level
        thinking_map = {"off": 0, "low": 4096, "medium": 8192, "high": 16384}
        config.agent.thinking_budget = thinking_map.get(params.thinking_level, 4096)

        # Resolve provider from config — matches orchestrator._resolve_provider()
        providers_config = config.providers
        default = providers_config.default
        profile = providers_config.profiles.get(default)

        if default == "anthropic":
            provider = AnthropicProvider(
                api_key=profile.api_key if profile else None,
                base_url=profile.base_url if profile else None,
                default_model=(profile.model or config.agent.model) if profile else config.agent.model,
            )
        elif default == "openai":
            provider = OpenAIProvider(
                api_key=profile.api_key if profile else None,
                base_url=profile.base_url if profile else None,
            )
        elif default == "ollama":
            provider = OllamaProvider(
                base_url=profile.base_url if profile else "http://localhost:11434",
                default_model=profile.model if profile else "llama3.1",
            )
        elif default == "openrouter":
            from predator.providers.openrouter import OpenRouterProvider
            provider = OpenRouterProvider(
                api_key=profile.api_key if profile else None,
            )
        else:
            provider = AnthropicProvider(default_model=config.agent.model)

        registry = create_default_registry()
        transcript = SessionTranscript(record.session_key, record.agent_id)
        hook_runner = HookRunner()

        runtime = AgentRuntime(
            provider=provider,
            registry=registry,
            config=config,
            hook_runner=hook_runner,
            transcript=transcript,
            lane=CommandLane.SUBAGENT,
        )

        return runtime

    # ── Steering & Control ──────────────────────────────────────

    async def steer(self, run_id: str, message: str) -> bool:
        """Send a steering message to a running subagent.

        Steering messages are injected into the subagent's next turn
        as additional user context.
        """
        record = self._registry.get(run_id)
        if not record or record.is_done:
            return False

        if run_id not in self._steering_messages:
            self._steering_messages[run_id] = []
        self._steering_messages[run_id].append(message)

        log.info(f"Steering message sent to subagent {run_id}: {message[:100]}")
        return True

    def get_steering_messages(self, run_id: str) -> list[str]:
        """Get and clear pending steering messages for a subagent."""
        return self._steering_messages.pop(run_id, [])

    async def kill(self, run_id: str) -> bool:
        """Kill a running subagent."""
        record = self._registry.get(run_id)
        if not record or record.is_done:
            return False

        if record._task_handle and not record._task_handle.done():
            record._task_handle.cancel()
            log.info(f"Killed subagent {run_id}")
            return True

        return False

    async def wait(
        self, run_id: str, timeout: float = 600,
    ) -> Optional[SubagentRunRecord]:
        """Wait for a subagent to complete."""
        return await self._registry.wait_for_completion(run_id, timeout)

    def get_children(self, parent_session_key: str) -> list[SubagentRunRecord]:
        return self._registry.get_children(parent_session_key)

    def get_active_children(self, parent_session_key: str) -> list[SubagentRunRecord]:
        return self._registry.get_active_children(parent_session_key)

    def get_all_records(self) -> list[SubagentRunRecord]:
        return self._registry.all_records()


# ═══════════════════════════════════════════════════════════════════
# Module-level singleton
# ═══════════════════════════════════════════════════════════════════

_global_spawner: Optional[SubagentSpawner] = None


def get_spawner() -> SubagentSpawner:
    """Get or create the global SubagentSpawner singleton."""
    global _global_spawner
    if _global_spawner is None:
        _global_spawner = SubagentSpawner()
    return _global_spawner


def set_spawner(spawner: SubagentSpawner) -> None:
    """Set the global SubagentSpawner (used by gateway)."""
    global _global_spawner
    _global_spawner = spawner
