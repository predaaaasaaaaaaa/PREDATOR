"""Memory store — simple file-based knowledge persistence.

Mirrors OpenClaw's memory manager at a simpler level for V1.
Stores investigation notes, findings, and intelligence in structured files.
"""

from __future__ import annotations

import json
import time
from pathlib import Path
from typing import Any, Optional

from predator.config.paths import get_memory_dir
from predator.utils.logger import get_logger

log = get_logger("memory.store")


class MemoryStore:
    """File-based memory store for persistent knowledge.

    Stores:
    - Investigation notes and findings
    - Target profiles
    - Tool output summaries
    - OSINT intelligence
    """

    def __init__(self, base_dir: Optional[Path] = None) -> None:
        self._dir = base_dir or get_memory_dir()
        self._index_file = self._dir / "index.json"
        self._index: dict[str, dict[str, Any]] = {}
        self._load_index()

    def _load_index(self) -> None:
        """Load the memory index."""
        if self._index_file.exists():
            try:
                with open(self._index_file) as f:
                    self._index = json.load(f)
            except (json.JSONDecodeError, OSError):
                self._index = {}

    def _save_index(self) -> None:
        """Save the memory index."""
        try:
            with open(self._index_file, "w") as f:
                json.dump(self._index, f, indent=2, default=str)
        except OSError as e:
            log.error(f"Failed to save memory index: {e}")

    def store(
        self,
        key: str,
        content: str,
        category: str = "general",
        tags: Optional[list[str]] = None,
        metadata: Optional[dict[str, Any]] = None,
    ) -> None:
        """Store a memory entry."""
        entry_file = self._dir / f"{key}.md"

        # Write content
        with open(entry_file, "w", encoding="utf-8") as f:
            f.write(content)

        # Update index
        self._index[key] = {
            "category": category,
            "tags": tags or [],
            "metadata": metadata or {},
            "created_at": time.time(),
            "updated_at": time.time(),
            "size": len(content),
        }
        self._save_index()

    def retrieve(self, key: str) -> Optional[str]:
        """Retrieve a memory entry by key."""
        entry_file = self._dir / f"{key}.md"
        if entry_file.exists():
            return entry_file.read_text(encoding="utf-8")
        return None

    def search(
        self,
        query: str = "",
        category: Optional[str] = None,
        tags: Optional[list[str]] = None,
        max_results: int = 10,
    ) -> list[dict[str, Any]]:
        """Search memory entries."""
        results: list[dict[str, Any]] = []

        for key, meta in self._index.items():
            # Filter by category
            if category and meta.get("category") != category:
                continue

            # Filter by tags
            if tags and not set(tags).intersection(set(meta.get("tags", []))):
                continue

            # Search in content if query provided
            if query:
                content = self.retrieve(key)
                if content and query.lower() not in content.lower():
                    continue

            results.append({"key": key, **meta})

            if len(results) >= max_results:
                break

        return results

    def delete(self, key: str) -> bool:
        """Delete a memory entry."""
        entry_file = self._dir / f"{key}.md"
        if key in self._index:
            del self._index[key]
            self._save_index()
        if entry_file.exists():
            entry_file.unlink()
            return True
        return False

    def list_all(self) -> list[dict[str, Any]]:
        """List all memory entries."""
        return [{"key": k, **v} for k, v in self._index.items()]

    @property
    def count(self) -> int:
        return len(self._index)
