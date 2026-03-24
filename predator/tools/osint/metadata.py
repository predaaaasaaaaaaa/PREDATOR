"""Metadata OSINT tools — ExifTool for image/document metadata extraction."""

from __future__ import annotations

from typing import Any, Callable, Optional

from predator.process.executor import ExecOptions, execute
from predator.tools.base import BaseTool, ToolCategory, ToolResult


class ExifTool(BaseTool):
    """Extract metadata from files (images, PDFs, documents)."""

    name = "exiftool"
    description = (
        "Extract and analyze metadata from files using ExifTool. "
        "Reads EXIF, IPTC, XMP, GPS coordinates, device info, timestamps, "
        "author names, and more from images, PDFs, Office documents, audio, "
        "and video files. Critical for OSINT geolocation and attribution."
    )
    category = ToolCategory.OSINT

    def get_parameters(self) -> dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "file": {
                    "type": "string",
                    "description": "Path to the file to analyze",
                },
                "tags": {
                    "type": "string",
                    "description": "Specific tags to extract (e.g., '-GPS*', '-Author')",
                },
                "recursive": {
                    "type": "boolean",
                    "description": "Process files recursively in directory",
                },
                "json_output": {
                    "type": "boolean",
                    "description": "Output in JSON format (default: false)",
                },
                "gps_only": {
                    "type": "boolean",
                    "description": "Extract only GPS/location data (default: false)",
                },
            },
            "required": ["file"],
        }

    async def execute(
        self, tool_call_id: str, arguments: dict[str, Any],
        on_update: Optional[Callable[[str], None]] = None,
    ) -> ToolResult:
        file_path = arguments["file"]
        tags = arguments.get("tags", "")
        recursive = arguments.get("recursive", False)
        json_output = arguments.get("json_output", False)
        gps_only = arguments.get("gps_only", False)

        cmd_parts = ["exiftool"]

        if gps_only:
            cmd_parts.append("-GPS*")
        elif tags:
            cmd_parts.append(tags)

        if recursive:
            cmd_parts.append("-r")

        if json_output:
            cmd_parts.append("-json")

        cmd_parts.append(f"'{file_path}'")
        cmd = " ".join(cmd_parts)

        result = await execute(
            ExecOptions(command=cmd, timeout=60, tool_call_id=tool_call_id),
        )
        return ToolResult(
            output=result.stdout or result.stderr,
            is_error=result.exit_code != 0 and not result.stdout,
            metadata={"file": file_path, "command": cmd, "elapsed": round(result.elapsed, 2)},
        )
