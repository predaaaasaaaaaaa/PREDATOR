"""Bootstrap and entry point for PREDATOR — mirrors OpenClaw's entry.ts.

Handles:
- Platform validation (Linux only)
- Environment setup (.env loading)
- Profile support (--profile flag for isolated state)
- CLI dispatch
"""

from __future__ import annotations

import os
import sys


def _assert_platform() -> None:
    """PREDATOR only runs on Linux (Kali focus, any distro supported).

    Set PREDATOR_DEV=1 to bypass for development on non-Linux machines.
    """
    if sys.platform != "linux" and not os.environ.get("PREDATOR_DEV"):
        from rich.console import Console

        console = Console(stderr=True)
        console.print(
            "[bold red]PREDATOR is designed for Linux systems only "
            "(Kali Linux recommended).[/bold red]\n"
            f"Detected platform: {sys.platform}\n"
            "[dim]Set PREDATOR_DEV=1 to bypass for development.[/dim]\n"
            "Exiting."
        )
        sys.exit(1)


def _load_env() -> None:
    """Load .env files — mirrors OpenClaw's dotenv loading."""
    try:
        from dotenv import load_dotenv

        # Load from PREDATOR state dir
        state_dir = os.environ.get(
            "PREDATOR_STATE_DIR",
            os.path.expanduser("~/.predator"),
        )
        env_file = os.path.join(state_dir, ".env")
        if os.path.isfile(env_file):
            load_dotenv(env_file)

        # Load from cwd
        if os.path.isfile(".env"):
            load_dotenv(".env", override=False)
    except ImportError:
        pass


def _apply_profile(argv: list[str]) -> list[str]:
    """Extract --profile flag and set PREDATOR_PROFILE env var.

    Mirrors OpenClaw's applyCliProfileEnv() for isolated state directories.
    """
    clean_argv: list[str] = []
    i = 0
    while i < len(argv):
        if argv[i] == "--profile" and i + 1 < len(argv):
            os.environ["PREDATOR_PROFILE"] = argv[i + 1]
            i += 2
        elif argv[i].startswith("--profile="):
            os.environ["PREDATOR_PROFILE"] = argv[i].split("=", 1)[1]
            i += 1
        else:
            clean_argv.append(argv[i])
            i += 1
    return clean_argv


def main() -> None:
    """Main entry point — called by `predator` CLI or `python -m predator`."""
    # Platform gate
    _assert_platform()

    # Environment
    _load_env()

    # Profile support
    argv = _apply_profile(sys.argv[1:])

    # Import and run CLI
    from predator.cli.program import cli

    cli(args=argv, standalone_mode=True)


if __name__ == "__main__":
    main()
