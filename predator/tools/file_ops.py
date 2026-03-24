"""File operation tools — mirrors OpenClaw's file-related agent capabilities.

Provides read, write, list, search, and grep operations.
"""

from __future__ import annotations

import fnmatch
import os
from pathlib import Path
from typing import Any, Callable, Optional

from predator.tools.base import BaseTool, ToolCategory, ToolResult


class ReadFileTool(BaseTool):
    """Read file contents."""

    name = "read_file"
    description = (
        "Read the contents of a file. Supports text files, config files, logs, "
        "scripts, and any readable file on the system."
    )
    category = ToolCategory.SYSTEM

    def get_parameters(self) -> dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "path": {"type": "string", "description": "Absolute path to the file"},
                "offset": {
                    "type": "number",
                    "description": "Line number to start reading from (1-based)",
                },
                "limit": {
                    "type": "number",
                    "description": "Maximum number of lines to read",
                },
            },
            "required": ["path"],
        }

    async def execute(
        self, tool_call_id: str, arguments: dict[str, Any],
        on_update: Optional[Callable[[str], None]] = None,
    ) -> ToolResult:
        path = arguments["path"]
        offset = int(arguments.get("offset", 1))
        limit = int(arguments.get("limit", 2000))

        try:
            p = Path(path).expanduser().resolve()
            if not p.is_file():
                return ToolResult(output=f"File not found: {path}", is_error=True)

            with open(p, "r", errors="replace") as f:
                lines = f.readlines()

            start = max(0, offset - 1)
            end = start + limit
            selected = lines[start:end]

            numbered = []
            for i, line in enumerate(selected, start=start + 1):
                numbered.append(f"{i:6d}\t{line.rstrip()}")

            output = "\n".join(numbered) if numbered else "(empty file)"
            return ToolResult(
                output=output,
                metadata={"total_lines": len(lines), "shown": len(selected)},
            )
        except Exception as e:
            return ToolResult(output=f"Error reading file: {e}", is_error=True)


class WriteFileTool(BaseTool):
    """Write content to a file."""

    name = "write_file"
    description = "Write content to a file. Creates parent directories if needed."
    category = ToolCategory.SYSTEM

    def get_parameters(self) -> dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "path": {"type": "string", "description": "Absolute path to the file"},
                "content": {"type": "string", "description": "Content to write"},
                "append": {
                    "type": "boolean",
                    "description": "Append instead of overwrite (default: false)",
                },
            },
            "required": ["path", "content"],
        }

    async def execute(
        self, tool_call_id: str, arguments: dict[str, Any],
        on_update: Optional[Callable[[str], None]] = None,
    ) -> ToolResult:
        path = arguments["path"]
        content = arguments["content"]
        append = arguments.get("append", False)

        try:
            p = Path(path).expanduser().resolve()
            p.parent.mkdir(parents=True, exist_ok=True)
            mode = "a" if append else "w"
            with open(p, mode) as f:
                f.write(content)
            return ToolResult(
                output=f"Successfully wrote {len(content)} bytes to {path}",
                metadata={"bytes_written": len(content)},
            )
        except Exception as e:
            return ToolResult(output=f"Error writing file: {e}", is_error=True)


class ListDirectoryTool(BaseTool):
    """List directory contents."""

    name = "list_directory"
    description = "List files and directories at a given path with details."
    category = ToolCategory.SYSTEM

    def get_parameters(self) -> dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "path": {
                    "type": "string",
                    "description": "Directory path to list (default: current dir)",
                },
                "all": {
                    "type": "boolean",
                    "description": "Include hidden files (default: false)",
                },
            },
            "required": [],
        }

    async def execute(
        self, tool_call_id: str, arguments: dict[str, Any],
        on_update: Optional[Callable[[str], None]] = None,
    ) -> ToolResult:
        path = arguments.get("path", ".")
        show_all = arguments.get("all", False)

        try:
            p = Path(path).expanduser().resolve()
            if not p.is_dir():
                return ToolResult(output=f"Not a directory: {path}", is_error=True)

            entries = sorted(p.iterdir(), key=lambda x: (not x.is_dir(), x.name.lower()))
            lines = []
            for entry in entries:
                if not show_all and entry.name.startswith("."):
                    continue
                prefix = "d " if entry.is_dir() else "f "
                try:
                    size = entry.stat().st_size if entry.is_file() else 0
                    size_str = _format_size(size) if size else ""
                except OSError:
                    size_str = ""
                lines.append(f"{prefix}{entry.name:<60s} {size_str}")

            return ToolResult(
                output="\n".join(lines) if lines else "(empty directory)",
                metadata={"count": len(lines)},
            )
        except Exception as e:
            return ToolResult(output=f"Error listing directory: {e}", is_error=True)


class SearchFilesTool(BaseTool):
    """Search for files by pattern."""

    name = "search_files"
    description = (
        "Search for files matching a glob pattern. "
        "Useful for finding config files, scripts, logs, etc."
    )
    category = ToolCategory.SYSTEM

    def get_parameters(self) -> dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "pattern": {
                    "type": "string",
                    "description": "Glob pattern (e.g., '**/*.py', '*.conf')",
                },
                "path": {
                    "type": "string",
                    "description": "Root directory to search from (default: current dir)",
                },
                "max_results": {
                    "type": "number",
                    "description": "Maximum results to return (default: 50)",
                },
            },
            "required": ["pattern"],
        }

    async def execute(
        self, tool_call_id: str, arguments: dict[str, Any],
        on_update: Optional[Callable[[str], None]] = None,
    ) -> ToolResult:
        pattern = arguments["pattern"]
        root = arguments.get("path", ".")
        max_results = int(arguments.get("max_results", 50))

        try:
            p = Path(root).expanduser().resolve()
            matches = list(p.glob(pattern))[:max_results]
            lines = [str(m) for m in sorted(matches)]
            return ToolResult(
                output="\n".join(lines) if lines else f"No files matching '{pattern}'",
                metadata={"count": len(lines)},
            )
        except Exception as e:
            return ToolResult(output=f"Error searching files: {e}", is_error=True)


class GrepTool(BaseTool):
    """Search file contents with regex."""

    name = "grep"
    description = (
        "Search for a pattern in file contents using regex. "
        "Returns matching lines with file paths and line numbers."
    )
    category = ToolCategory.SYSTEM

    def get_parameters(self) -> dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "pattern": {
                    "type": "string",
                    "description": "Regex pattern to search for",
                },
                "path": {
                    "type": "string",
                    "description": "File or directory to search in (default: current dir)",
                },
                "glob": {
                    "type": "string",
                    "description": "File glob filter (e.g., '*.py')",
                },
                "case_insensitive": {
                    "type": "boolean",
                    "description": "Case insensitive search (default: false)",
                },
                "max_results": {
                    "type": "number",
                    "description": "Maximum results (default: 100)",
                },
            },
            "required": ["pattern"],
        }

    async def execute(
        self, tool_call_id: str, arguments: dict[str, Any],
        on_update: Optional[Callable[[str], None]] = None,
    ) -> ToolResult:
        import re

        pattern_str = arguments["pattern"]
        path = arguments.get("path", ".")
        file_glob = arguments.get("glob", "**/*")
        case_insensitive = arguments.get("case_insensitive", False)
        max_results = int(arguments.get("max_results", 100))

        flags = re.IGNORECASE if case_insensitive else 0

        try:
            regex = re.compile(pattern_str, flags)
        except re.error as e:
            return ToolResult(output=f"Invalid regex: {e}", is_error=True)

        try:
            p = Path(path).expanduser().resolve()
            results = []
            files = [p] if p.is_file() else list(p.glob(file_glob))

            for file_path in files:
                if not file_path.is_file():
                    continue
                try:
                    with open(file_path, "r", errors="replace") as f:
                        for i, line in enumerate(f, 1):
                            if regex.search(line):
                                results.append(f"{file_path}:{i}: {line.rstrip()}")
                                if len(results) >= max_results:
                                    break
                except (OSError, UnicodeDecodeError):
                    continue
                if len(results) >= max_results:
                    break

            output = "\n".join(results) if results else f"No matches for '{pattern_str}'"
            return ToolResult(output=output, metadata={"matches": len(results)})
        except Exception as e:
            return ToolResult(output=f"Error searching: {e}", is_error=True)


def _format_size(size: int) -> str:
    """Format file size in human-readable form."""
    for unit in ("B", "KB", "MB", "GB"):
        if size < 1024:
            return f"{size:>8.1f} {unit}"
        size /= 1024
    return f"{size:>8.1f} TB"
