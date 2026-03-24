"""Workspace file loader — discovers and loads .md files for agent system prompt.

Mirrors OpenClaw's buildAgentSystemPrompt() workspace file injection.
Loads: AGENTS.md, SOUL.md, HEARTBEAT.md, BOOTSTRAP.md, IDENTITY.md, USER.md, TOOLS.md, BOOT.md, MEMORY.md
"""

from __future__ import annotations

import time
from pathlib import Path
from typing import Optional

from predator.utils.logger import get_logger

log = get_logger("agents.workspace")

# Files loaded for main agent sessions (full context)
MAIN_SESSION_FILES = [
    "AGENTS.md",
    "SOUL.md",
    "IDENTITY.md",
    "USER.md",
    "TOOLS.md",
    "MEMORY.md",
    "HEARTBEAT.md",
    "BOOT.md",
    "BOOTSTRAP.md",
]

# Files loaded for subagent / cron sessions (minimal context)
MINIMAL_SESSION_FILES = [
    "SOUL.md",
    "IDENTITY.md",
]

# Per-file max size (chars)
MAX_FILE_CHARS = 20_000

# Total max chars across all files
MAX_TOTAL_CHARS = 150_000

# Cache TTL in seconds
CACHE_TTL = 30


class WorkspaceFiles:
    """Discovers and loads workspace .md files with caching."""

    def __init__(self, workspace_dir: Optional[Path | str] = None) -> None:
        self._workspace_dir = Path(workspace_dir) if workspace_dir else None
        self._cache: dict[str, tuple[float, str]] = {}  # filename -> (timestamp, content)

    def _resolve_dir(self) -> Path:
        """Resolve the workspace directory.

        Checks (in order):
        1. Explicit workspace_dir
        2. PREDATOR templates directory (bundled defaults)
        """
        if self._workspace_dir and self._workspace_dir.is_dir():
            return self._workspace_dir

        # Fall back to bundled templates
        templates = Path(__file__).parent.parent.parent / "templates"
        if templates.is_dir():
            return templates

        return Path.cwd()

    def _read_file(self, filepath: Path) -> str:
        """Read a file with size limit and caching."""
        name = filepath.name
        now = time.time()

        # Check cache
        if name in self._cache:
            cached_time, cached_content = self._cache[name]
            if now - cached_time < CACHE_TTL:
                return cached_content

        if not filepath.exists():
            return ""

        try:
            content = filepath.read_text(encoding="utf-8")
            # Truncate if too large
            if len(content) > MAX_FILE_CHARS:
                content = content[:MAX_FILE_CHARS] + "\n\n[... truncated at 20K chars ...]"
            self._cache[name] = (now, content)
            return content
        except Exception as e:
            log.warning(f"Failed to read {filepath}: {e}")
            return ""

    def load_files(self, session_type: str = "main") -> dict[str, str]:
        """Load workspace files based on session type.

        Args:
            session_type: "main" for full context, "subagent" or "cron" for minimal.

        Returns:
            Dict of filename -> content for files that exist and have content.
        """
        workspace = self._resolve_dir()

        if session_type == "main":
            filenames = MAIN_SESSION_FILES
        else:
            filenames = MINIMAL_SESSION_FILES

        result: dict[str, str] = {}
        total_chars = 0

        for name in filenames:
            filepath = workspace / name
            content = self._read_file(filepath)
            if not content:
                continue

            # Check total budget
            if total_chars + len(content) > MAX_TOTAL_CHARS:
                remaining = MAX_TOTAL_CHARS - total_chars
                if remaining > 500:
                    content = content[:remaining] + "\n\n[... truncated due to total size limit ...]"
                else:
                    log.info(f"Skipping {name} — total size limit reached")
                    continue

            result[name] = content
            total_chars += len(content)

        return result

    def build_prompt_section(self, session_type: str = "main") -> str:
        """Build the workspace files section for the system prompt.

        Returns a formatted string with all loaded files, ready to inject.
        """
        files = self.load_files(session_type)

        if not files:
            return ""

        parts: list[str] = []
        parts.append("# Workspace Files\n")

        for name, content in files.items():
            # Strip the .md extension for section headers
            label = name.replace(".md", "")
            parts.append(f"## {label}\n\n{content}\n")

        return "\n".join(parts)

    def has_bootstrap(self) -> bool:
        """Check if BOOTSTRAP.md exists (first-run detection)."""
        workspace = self._resolve_dir()
        return (workspace / "BOOTSTRAP.md").exists()

    def delete_bootstrap(self) -> bool:
        """Delete BOOTSTRAP.md after first-run ritual completes."""
        workspace = self._resolve_dir()
        bootstrap = workspace / "BOOTSTRAP.md"
        if bootstrap.exists():
            bootstrap.unlink()
            # Clear cache
            self._cache.pop("BOOTSTRAP.md", None)
            return True
        return False

    def get_heartbeat_content(self) -> str:
        """Get HEARTBEAT.md content (used by heartbeat runner)."""
        workspace = self._resolve_dir()
        return self._read_file(workspace / "HEARTBEAT.md")

    def update_file(self, filename: str, content: str) -> None:
        """Update a workspace file (used during bootstrap, identity updates, etc.)."""
        workspace = self._resolve_dir()
        filepath = workspace / filename
        filepath.write_text(content, encoding="utf-8")
        # Invalidate cache
        self._cache.pop(filename, None)
