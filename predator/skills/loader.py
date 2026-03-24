"""Skill loader — mirrors OpenClaw's SKILL.md-based skill system.

Skills are Markdown files with YAML frontmatter that define
specialized capabilities for the agent.
"""

from __future__ import annotations

import os
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Optional

import yaml

from predator.config.paths import get_skills_dir
from predator.utils.logger import get_logger

log = get_logger("skills.loader")


@dataclass
class Skill:
    """A loaded skill definition."""

    id: str
    name: str
    description: str
    prompt: str
    category: str = "general"
    tools: list[str] = field(default_factory=list)
    requires: list[str] = field(default_factory=list)
    tags: list[str] = field(default_factory=list)
    version: str = "1.0.0"
    author: str = ""

    @property
    def summary(self) -> str:
        return f"{self.name}: {self.description}"


def _parse_skill_md(content: str) -> tuple[dict[str, Any], str]:
    """Parse a SKILL.md file with YAML frontmatter."""
    if content.startswith("---"):
        parts = content.split("---", 2)
        if len(parts) >= 3:
            frontmatter = yaml.safe_load(parts[1]) or {}
            body = parts[2].strip()
            return frontmatter, body
    return {}, content


class SkillLoader:
    """Loads and manages PREDATOR skills.

    Mirrors OpenClaw's skill loading:
    - Scans skill directories for SKILL.md files
    - Parses YAML frontmatter + Markdown body
    - Makes skills available to the agent
    """

    def __init__(self) -> None:
        self._skills: dict[str, Skill] = {}

    def load_directory(self, directory: Path) -> int:
        """Load all skills from a directory."""
        count = 0
        if not directory.is_dir():
            return 0

        for entry in directory.iterdir():
            if entry.is_dir():
                skill_file = entry / "SKILL.md"
                if skill_file.exists():
                    skill = self._load_file(skill_file, entry.name)
                    if skill:
                        self._skills[skill.id] = skill
                        count += 1
            elif entry.suffix == ".md" and entry.name != "README.md":
                skill = self._load_file(entry, entry.stem)
                if skill:
                    self._skills[skill.id] = skill
                    count += 1

        log.info(f"Loaded {count} skills from {directory}")
        return count

    def _load_file(self, path: Path, default_id: str) -> Optional[Skill]:
        """Load a single skill file."""
        try:
            content = path.read_text(encoding="utf-8")
            meta, body = _parse_skill_md(content)

            return Skill(
                id=meta.get("id", default_id),
                name=meta.get("name", default_id.replace("-", " ").title()),
                description=meta.get("description", ""),
                prompt=body,
                category=meta.get("category", "general"),
                tools=meta.get("tools", []),
                requires=meta.get("requires", []),
                tags=meta.get("tags", []),
                version=meta.get("version", "1.0.0"),
                author=meta.get("author", ""),
            )
        except Exception as e:
            log.error(f"Failed to load skill from {path}: {e}")
            return None

    def load_defaults(self) -> int:
        """Load skills from all default locations."""
        count = 0

        # Built-in skills (in the PREDATOR package)
        builtin_dir = Path(__file__).parent.parent.parent / "skills"
        if builtin_dir.is_dir():
            count += self.load_directory(builtin_dir)

        # User skills (~/.predator/skills/)
        user_dir = get_skills_dir()
        count += self.load_directory(user_dir)

        return count

    def get(self, skill_id: str) -> Optional[Skill]:
        return self._skills.get(skill_id)

    def get_all(self) -> list[Skill]:
        return list(self._skills.values())

    def get_by_category(self, category: str) -> list[Skill]:
        return [s for s in self._skills.values() if s.category == category]

    def search(self, query: str) -> list[Skill]:
        query_lower = query.lower()
        return [
            s for s in self._skills.values()
            if query_lower in s.name.lower()
            or query_lower in s.description.lower()
            or any(query_lower in t for t in s.tags)
        ]

    @property
    def count(self) -> int:
        return len(self._skills)
