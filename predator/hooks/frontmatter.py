"""Hook frontmatter parser — extracts YAML metadata from hook files.

PREDATOR supports defining hooks as ``.hook.py`` or ``.hook.sh`` files with
YAML frontmatter.  The frontmatter block is delimited by ``---`` and must
appear at the very start of the file (inside a comment block for code files).

Example ``.hook.py`` file::

    # ---
    # name: my-hook
    # event: tool:before
    # priority: 50
    # enabled: true
    # description: "Logs all tool calls"
    # ---

This module provides two public helpers:

* :func:`parse_hook_frontmatter` — reads a single file and returns parsed
  frontmatter as a plain ``dict``.
* :func:`discover_hooks` — scans a directory for hook files and returns a
  list of dicts (frontmatter + file path).
"""

from __future__ import annotations

import os
from pathlib import Path
from typing import Any, Optional

import yaml

from predator.utils.logger import get_logger

log = get_logger("hooks.frontmatter")

# File extensions recognised as hook files
HOOK_EXTENSIONS = (".hook.py", ".hook.sh")


def _strip_comment_prefixes(line: str) -> str:
    """Remove leading ``#`` or ``//`` comment markers (with optional space)."""
    stripped = line.lstrip()
    if stripped.startswith("# "):
        return stripped[2:]
    if stripped.startswith("#"):
        return stripped[1:]
    if stripped.startswith("// "):
        return stripped[3:]
    if stripped.startswith("//"):
        return stripped[2:]
    return stripped


def parse_hook_frontmatter(path: str) -> dict:
    """Read a file at *path* and extract YAML frontmatter.

    The frontmatter must be the first non-empty content in the file, wrapped
    between two ``---`` delimiters.  For ``.py`` and ``.sh`` files the
    delimiters are expected inside comment lines (e.g. ``# ---``).

    Returns a ``dict`` with the parsed YAML keys.  If the file has no valid
    frontmatter or cannot be read, an empty dict is returned.
    """
    try:
        text = Path(path).read_text(encoding="utf-8")
    except OSError as exc:
        log.warning("Cannot read hook file %s: %s", path, exc)
        return {}

    lines = text.splitlines()

    # --- Locate opening delimiter ---
    start_idx: Optional[int] = None
    for i, raw_line in enumerate(lines):
        cleaned = _strip_comment_prefixes(raw_line)
        if cleaned.strip() == "---":
            start_idx = i
            break
        # Allow blank lines / shebangs before the opening delimiter
        if raw_line.strip() and not raw_line.strip().startswith("#!"):
            break

    if start_idx is None:
        return {}

    # --- Locate closing delimiter ---
    yaml_lines: list[str] = []
    end_idx: Optional[int] = None
    for j in range(start_idx + 1, len(lines)):
        cleaned = _strip_comment_prefixes(lines[j])
        if cleaned.strip() == "---":
            end_idx = j
            break
        yaml_lines.append(cleaned)

    if end_idx is None:
        return {}

    raw_yaml = "\n".join(yaml_lines).strip()
    if not raw_yaml:
        return {}

    try:
        data: dict[str, Any] = yaml.safe_load(raw_yaml) or {}
    except yaml.YAMLError as exc:
        log.warning("Failed to parse hook frontmatter YAML in %s: %s", path, exc)
        return {}

    if not isinstance(data, dict):
        return {}

    return data


def discover_hooks(directory: str) -> list[dict]:
    """Scan *directory* for hook files and return parsed metadata.

    Each entry in the returned list is a dict containing all frontmatter
    keys plus a ``path`` key pointing to the absolute file path.  Files
    whose frontmatter is empty or cannot be parsed are silently skipped.

    Only files ending with ``.hook.py`` or ``.hook.sh`` are considered.
    """
    results: list[dict] = []
    dir_path = Path(directory)

    if not dir_path.is_dir():
        log.warning("Hook directory does not exist: %s", directory)
        return results

    for root, _dirs, files in os.walk(dir_path):
        for fname in sorted(files):
            if not any(fname.endswith(ext) for ext in HOOK_EXTENSIONS):
                continue
            full_path = os.path.join(root, fname)
            meta = parse_hook_frontmatter(full_path)
            if not meta:
                continue
            meta["path"] = full_path
            results.append(meta)

    # Sort by priority (lower = first), defaulting to 100
    results.sort(key=lambda m: m.get("priority", 100))
    return results
