"""Logging infrastructure for PREDATOR — mirrors OpenClaw's logger.ts.

Provides structured logging with Rich formatting, file logging,
and per-module log levels.
"""

from __future__ import annotations

import logging
import os
from pathlib import Path
from typing import Optional

from rich.console import Console
from rich.logging import RichHandler

_LOG_DIR: Optional[Path] = None
_CONSOLE = Console(stderr=True)


def _resolve_log_dir() -> Path:
    """Resolve the PREDATOR log directory."""
    state_dir = os.environ.get("PREDATOR_STATE_DIR", os.path.expanduser("~/.predator"))
    log_dir = Path(state_dir) / "logs"
    log_dir.mkdir(parents=True, exist_ok=True)
    return log_dir


def get_log_dir() -> Path:
    """Get or create the log directory."""
    global _LOG_DIR
    if _LOG_DIR is None:
        _LOG_DIR = _resolve_log_dir()
    return _LOG_DIR


def setup_logging(verbose: bool = False, debug: bool = False) -> None:
    """Configure PREDATOR logging with Rich console + file output."""
    level = logging.DEBUG if debug else (logging.INFO if verbose else logging.WARNING)

    # Console handler via Rich
    rich_handler = RichHandler(
        console=_CONSOLE,
        show_time=True,
        show_path=debug,
        markup=True,
        rich_tracebacks=True,
        tracebacks_show_locals=debug,
    )
    rich_handler.setLevel(level)

    # File handler
    log_file = get_log_dir() / "predator.log"
    file_handler = logging.FileHandler(str(log_file), encoding="utf-8")
    file_handler.setLevel(logging.DEBUG)
    file_handler.setFormatter(
        logging.Formatter("%(asctime)s | %(name)s | %(levelname)s | %(message)s")
    )

    # Root logger
    root = logging.getLogger("predator")
    root.setLevel(logging.DEBUG)
    root.handlers.clear()
    root.addHandler(rich_handler)
    root.addHandler(file_handler)


def get_logger(name: str) -> logging.Logger:
    """Get a namespaced PREDATOR logger."""
    return logging.getLogger(f"predator.{name}")
