"""Plugin manifest schema — Pydantic model for plugin.yaml files.

Defines the structure every plugin must declare in its plugin.yaml manifest,
including metadata, tool/hook registrations, config schema, and dependencies.
"""

from __future__ import annotations

from typing import Any, Optional

from pydantic import BaseModel, Field


class HookDefinition(BaseModel):
    """A hook declared in a plugin manifest."""

    event: str = Field(..., description="Hook event name (e.g. 'tool_execute_before')")
    handler: str = Field(..., description="Dotted path to the handler callable")
    priority: int = Field(default=100, description="Execution priority (lower = earlier)")
    filter: Optional[dict[str, Any]] = Field(
        default=None, description="Optional event filter criteria"
    )


class PluginManifestSchema(BaseModel):
    """Pydantic schema for plugin.yaml manifest files.

    Every plugin directory must contain a ``plugin.yaml`` that conforms to this
    schema.  The loader deserialises the YAML into this model for validation
    before the plugin is imported.
    """

    id: str = Field(..., description="Unique plugin identifier (e.g. 'predator-nmap')")
    name: str = Field(..., description="Human-readable plugin name")
    version: str = Field(default="1.0.0", description="Semver version string")
    description: str = Field(default="", description="Short description of the plugin")
    author: str = Field(default="", description="Plugin author or organisation")

    # Registrations
    tools: list[str] = Field(
        default_factory=list,
        description="List of dotted paths to tool classes (e.g. 'my_plugin.tools.NmapTool')",
    )
    hooks: list[HookDefinition] = Field(
        default_factory=list,
        description="List of hook definitions to register",
    )

    # Configuration
    config_schema: Optional[dict[str, Any]] = Field(
        default=None,
        description="Optional JSON Schema describing the plugin's config options",
    )

    # Dependencies
    dependencies: list[str] = Field(
        default_factory=list,
        description="pip package specifiers required by this plugin (e.g. 'nmap>=0.7')",
    )

    enabled: bool = Field(
        default=True,
        description="Whether the plugin is enabled (can be toggled in predator.yaml)",
    )
