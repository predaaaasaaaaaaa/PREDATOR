"""Memory tools — let the agent manage its own persistent knowledge.

Three tools:
- MemorySaveTool: Save a memory/finding to persistent storage.
- MemoryRecallTool: Recall memories by search query, category, or listing.
- MemoryTargetTool: Store and retrieve target intelligence profiles.
"""

from __future__ import annotations

import json
from typing import Any, Callable, Optional

from predator.memory.manager import MemoryManager
from predator.tools.base import BaseTool, ToolCategory, ToolResult
from predator.utils.logger import get_logger

log = get_logger("agents.tools.memory")


def _get_manager() -> MemoryManager:
    """Return a shared MemoryManager instance."""
    # Lazy singleton — avoids import-time side effects.
    if not hasattr(_get_manager, "_instance"):
        _get_manager._instance = MemoryManager()  # type: ignore[attr-defined]
    return _get_manager._instance  # type: ignore[attr-defined]


# ---------------------------------------------------------------------------
# MemorySaveTool
# ---------------------------------------------------------------------------

class MemorySaveTool(BaseTool):
    """Save a memory, finding, or note to persistent storage.

    Use this to remember important information between conversations —
    investigation findings, credentials, reconnaissance data, or notes.
    """

    name = "memory_save"
    description = (
        "Save a memory or finding to persistent storage. Use a descriptive "
        "key so you can recall it later. Categories help organise knowledge: "
        "'target' for target intel, 'finding' for discoveries, 'note' for "
        "general notes, 'credential' for credentials."
    )
    category = ToolCategory.MEMORY

    def get_parameters(self) -> dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "key": {
                    "type": "string",
                    "description": (
                        "Unique key for this memory (e.g. 'nmap-scan-10.0.0.1', "
                        "'finding-sqli-login'). Use descriptive, slug-style names."
                    ),
                },
                "content": {
                    "type": "string",
                    "description": "The content to store — text, markdown, JSON, etc.",
                },
                "category": {
                    "type": "string",
                    "description": "Category for organising this memory.",
                    "enum": ["target", "finding", "note", "credential"],
                },
            },
            "required": ["key", "content"],
        }

    def __init__(self, manager: Optional[MemoryManager] = None) -> None:
        self._manager = manager

    @property
    def manager(self) -> MemoryManager:
        return self._manager or _get_manager()

    async def execute(
        self,
        tool_call_id: str,
        arguments: dict[str, Any],
        on_update: Optional[Callable[[str], None]] = None,
    ) -> ToolResult:
        key = arguments.get("key", "").strip()
        content = arguments.get("content", "").strip()
        category = arguments.get("category", "note")

        if not key:
            return ToolResult(output="Missing required parameter: key", is_error=True)
        if not content:
            return ToolResult(output="Missing required parameter: content", is_error=True)

        try:
            self.manager.store.store(
                key=key,
                content=content,
                category=category,
                tags=[category],
            )
            log.info(f"Saved memory: {key} (category={category}, {len(content)} chars)")
            return ToolResult(
                output=f"Memory saved: '{key}' ({category}, {len(content)} chars)",
                metadata={"key": key, "category": category, "size": len(content)},
            )
        except Exception as exc:
            return ToolResult(
                output=f"Failed to save memory '{key}': {exc}",
                is_error=True,
            )


# ---------------------------------------------------------------------------
# MemoryRecallTool
# ---------------------------------------------------------------------------

class MemoryRecallTool(BaseTool):
    """Recall memories by search query, category, or listing all entries.

    Use this to retrieve previously stored findings, notes, and intelligence.
    """

    name = "memory_recall"
    description = (
        "Search and recall memories from persistent storage. You can search "
        "by text query, filter by category, or list recent memories. Returns "
        "matching entries with their content."
    )
    category = ToolCategory.MEMORY

    def get_parameters(self) -> dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "query": {
                    "type": "string",
                    "description": (
                        "Text to search for within memory content. "
                        "If omitted, returns all memories (filtered by category if given)."
                    ),
                },
                "category": {
                    "type": "string",
                    "description": "Filter by category: 'target', 'finding', 'note', 'credential', etc.",
                },
                "limit": {
                    "type": "number",
                    "description": "Maximum number of results to return (default 10).",
                },
            },
            "required": [],
        }

    def __init__(self, manager: Optional[MemoryManager] = None) -> None:
        self._manager = manager

    @property
    def manager(self) -> MemoryManager:
        return self._manager or _get_manager()

    async def execute(
        self,
        tool_call_id: str,
        arguments: dict[str, Any],
        on_update: Optional[Callable[[str], None]] = None,
    ) -> ToolResult:
        query = arguments.get("query", "")
        category = arguments.get("category")
        limit = int(arguments.get("limit", 10))

        try:
            results = self.manager.store.search(
                query=query,
                category=category,
                max_results=limit,
            )
        except Exception as exc:
            return ToolResult(output=f"Memory search failed: {exc}", is_error=True)

        if not results:
            parts = []
            if query:
                parts.append(f"query='{query}'")
            if category:
                parts.append(f"category='{category}'")
            filter_desc = ", ".join(parts) if parts else "no filters"
            return ToolResult(
                output=f"No memories found ({filter_desc}).",
                metadata={"result_count": 0},
            )

        # Format results — include content preview for each
        lines = [f"Found {len(results)} memory entries:\n"]
        for i, entry in enumerate(results, 1):
            key = entry.get("key", "?")
            cat = entry.get("category", "")
            tags = entry.get("tags", [])
            content = self.manager.store.retrieve(key) or ""
            preview = content[:300].replace("\n", " ")
            if len(content) > 300:
                preview += "..."

            lines.append(f"{i}. [{cat}] {key}")
            if tags:
                lines.append(f"   Tags: {', '.join(tags)}")
            lines.append(f"   {preview}")
            lines.append("")

        return ToolResult(
            output="\n".join(lines),
            metadata={
                "result_count": len(results),
                "keys": [e.get("key") for e in results],
            },
        )


# ---------------------------------------------------------------------------
# MemoryTargetTool
# ---------------------------------------------------------------------------

class MemoryTargetTool(BaseTool):
    """Store and retrieve intelligence profiles for targets.

    Targets are domains, IPs, organisations, people, etc.  Providing the
    ``data`` parameter stores (or merges) information; omitting it retrieves
    the existing profile.
    """

    name = "memory_target"
    description = (
        "Store or retrieve a target intelligence profile. If 'data' is "
        "provided, stores (or merges with existing) target intel. If 'data' "
        "is omitted, retrieves the current profile for the target."
    )
    category = ToolCategory.MEMORY

    def get_parameters(self) -> dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "target": {
                    "type": "string",
                    "description": (
                        "Target identifier — a domain, IP address, organisation name, "
                        "username, or other identifier."
                    ),
                },
                "data": {
                    "type": "object",
                    "description": (
                        "Intelligence data to store. If provided, this is merged "
                        "with any existing profile. If omitted, the tool retrieves "
                        "the current profile instead. Example: "
                        '{\"ports\": [80, 443], \"tech\": [\"nginx\", \"php\"]}'
                    ),
                },
            },
            "required": ["target"],
        }

    def __init__(self, manager: Optional[MemoryManager] = None) -> None:
        self._manager = manager

    @property
    def manager(self) -> MemoryManager:
        return self._manager or _get_manager()

    async def execute(
        self,
        tool_call_id: str,
        arguments: dict[str, Any],
        on_update: Optional[Callable[[str], None]] = None,
    ) -> ToolResult:
        target = arguments.get("target", "").strip()
        if not target:
            return ToolResult(output="Missing required parameter: target", is_error=True)

        data = arguments.get("data")

        # --- Store mode ---
        if data is not None:
            if not isinstance(data, dict):
                return ToolResult(
                    output="Parameter 'data' must be a JSON object.",
                    is_error=True,
                )
            try:
                self.manager.store_target(target, data)
                log.info(f"Stored target intel: {target} ({len(data)} fields)")
                return ToolResult(
                    output=(
                        f"Target profile updated: '{target}' "
                        f"({len(data)} fields merged)."
                    ),
                    metadata={"target": target, "mode": "store", "fields": list(data.keys())},
                )
            except Exception as exc:
                return ToolResult(
                    output=f"Failed to store target '{target}': {exc}",
                    is_error=True,
                )

        # --- Retrieve mode ---
        try:
            profile = self.manager.get_target(target)
        except Exception as exc:
            return ToolResult(
                output=f"Failed to retrieve target '{target}': {exc}",
                is_error=True,
            )

        if profile is None:
            return ToolResult(
                output=f"No profile found for target: '{target}'",
                metadata={"target": target, "mode": "retrieve", "found": False},
            )

        formatted = json.dumps(profile, indent=2, default=str)
        return ToolResult(
            output=f"Target profile for '{target}':\n\n{formatted}",
            metadata={"target": target, "mode": "retrieve", "found": True, "profile": profile},
        )
