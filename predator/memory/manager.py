"""Memory manager — high-level memory operations.

Mirrors OpenClaw's MemoryIndexManager with:
- Identity file (who is PREDATOR, user preferences)
- Investigation diary (daily summaries)
- Knowledge base search
"""

from __future__ import annotations

import time
from datetime import datetime
from pathlib import Path
from typing import Any, Optional

from predator.config.paths import get_memory_dir
from predator.memory.store import MemoryStore
from predator.utils.logger import get_logger

log = get_logger("memory.manager")


class MemoryManager:
    """High-level memory manager.

    Mirrors OpenClaw's memory patterns:
    - Identity file for persistent agent state
    - Investigation diary for session summaries
    - Target knowledge base
    - Tool output archive
    """

    def __init__(self, base_dir: Optional[Path] = None) -> None:
        self._dir = base_dir or get_memory_dir()
        self._store = MemoryStore(self._dir)
        self._identity_file = self._dir / "identity.md"
        self._diary_dir = self._dir / "diary"
        self._diary_dir.mkdir(parents=True, exist_ok=True)

    @property
    def store(self) -> MemoryStore:
        return self._store

    # --- Identity ---

    def get_identity(self) -> str:
        """Get the agent identity file content."""
        if self._identity_file.exists():
            return self._identity_file.read_text(encoding="utf-8")
        return ""

    def update_identity(self, content: str) -> None:
        """Update the agent identity file."""
        self._identity_file.write_text(content, encoding="utf-8")

    # --- Investigation Diary ---

    def add_diary_entry(self, summary: str, session_id: str = "default") -> None:
        """Add a diary entry for today's session."""
        today = datetime.now().strftime("%Y-%m-%d")
        diary_file = self._diary_dir / f"{today}.md"

        timestamp = datetime.now().strftime("%H:%M:%S")
        entry = f"\n## {timestamp} — Session: {session_id}\n\n{summary}\n"

        with open(diary_file, "a", encoding="utf-8") as f:
            f.write(entry)

    def get_diary(self, date: Optional[str] = None) -> str:
        """Get diary entries for a date (default: today)."""
        if date is None:
            date = datetime.now().strftime("%Y-%m-%d")
        diary_file = self._diary_dir / f"{date}.md"
        if diary_file.exists():
            return diary_file.read_text(encoding="utf-8")
        return ""

    def list_diary_dates(self) -> list[str]:
        """List all dates that have diary entries."""
        return sorted([p.stem for p in self._diary_dir.glob("*.md")])

    # --- Auto-Diary (called at end of agent runs) ---

    def auto_diary(self, session_id: str, message: str, response: str,
                   tools_used: list[str] | None = None, tokens: int = 0) -> None:
        """Automatically log agent activity to diary."""
        summary_parts = []
        summary_parts.append(f"**Query:** {message[:200]}")
        if tools_used:
            summary_parts.append(f"**Tools:** {', '.join(tools_used[:10])}")
        summary_parts.append(f"**Response preview:** {response[:300]}")
        if tokens:
            summary_parts.append(f"**Tokens:** {tokens}")
        self.add_diary_entry("\n".join(summary_parts), session_id)

    # --- Target Profiles ---

    def store_target(self, target: str, data: dict) -> None:
        """Store or update intelligence about a target."""
        import json as _json
        key = f"target-{target.replace('.', '-').replace('/', '-')}"
        existing = self._store.retrieve(key)
        if existing:
            try:
                old = _json.loads(existing)
                old.update(data)
                data = old
            except Exception:
                pass
        self._store.store(
            key=key,
            content=_json.dumps(data, indent=2, default=str),
            category="target",
            tags=["osint", target],
        )

    def get_target(self, target: str) -> dict | None:
        """Retrieve target intelligence."""
        import json as _json
        key = f"target-{target.replace('.', '-').replace('/', '-')}"
        content = self._store.retrieve(key)
        if content:
            try:
                return _json.loads(content)
            except Exception:
                return {"raw": content}
        return None

    # --- Tool Output Archive ---

    def archive_tool_output(self, tool_name: str, args: dict, output: str,
                            session_id: str = "default") -> None:
        """Archive significant tool output for future reference."""
        if len(output) < 50:
            return
        import hashlib
        key = f"tool-{tool_name}-{hashlib.md5(str(args).encode()).hexdigest()[:8]}"
        self._store.store(
            key=key,
            content=f"# {tool_name}\n**Args:** {args}\n**Output:**\n{output[:5000]}",
            category="tool_output",
            tags=[tool_name, session_id],
        )

    # --- Context for Agent ---

    def get_context_for_agent(self, max_chars: int = 2000) -> str:
        """Build memory context to inject into the agent's system prompt."""
        parts: list[str] = []

        # Identity
        identity = self.get_identity()
        if identity:
            parts.append(f"## Agent Identity\n{identity[:500]}")

        # Recent diary (last 20 lines)
        diary = self.get_diary()
        if diary:
            lines = diary.strip().split("\n")
            recent_diary = "\n".join(lines[-20:])
            parts.append(f"## Today's Investigation Log\n{recent_diary[:800]}")

        # Categorized memories
        all_memories = self._store.list_all()
        targets = [m for m in all_memories if m.get("category") == "target"][-3:]
        findings = [m for m in all_memories if m.get("category") == "finding"][-5:]
        recent = all_memories[-5:]

        if targets:
            parts.append("## Active Targets\n" + "\n".join(f"- {m['key']}" for m in targets))

        if findings:
            parts.append("## Recent Findings\n" + "\n".join(
                f"- [{m.get('category', '')}] {m['key']}" for m in findings
            ))
        elif recent:
            parts.append("## Recent Knowledge\n" + "\n".join(
                f"- [{m.get('category', '')}] {m['key']}" for m in recent
            ))

        context = "\n\n".join(parts)
        return context[:max_chars]
