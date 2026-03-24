"""Daemon service — mirrors OpenClaw's daemon/systemd.ts.

Linux-only systemd service management for persistent PREDATOR operation.
"""
from __future__ import annotations

import logging
import os
import subprocess
import sys
from typing import Optional

logger = logging.getLogger(__name__)

UNIT_TEMPLATE = """\
[Unit]
Description=PREDATOR Gateway{profile_suffix}
After=network-online.target
Wants=network-online.target

[Service]
ExecStart={exec_start}
Restart=always
RestartSec=5
KillMode=process
WorkingDirectory={work_dir}
Environment=PREDATOR_STATE_DIR={state_dir}
{extra_env}

[Install]
WantedBy=default.target
"""


class DaemonService:
    """Manages PREDATOR as a systemd user service."""

    def __init__(self, profile: str = ""):
        self._profile = profile
        self._service_name = f"predator-gateway{f'-{profile}' if profile else ''}"
        self._unit_dir = os.path.expanduser("~/.config/systemd/user")
        self._unit_path = os.path.join(self._unit_dir, f"{self._service_name}.service")

    @property
    def service_name(self) -> str:
        return self._service_name

    def _state_dir(self) -> str:
        base = os.environ.get("PREDATOR_STATE_DIR", os.path.expanduser("~/.predator"))
        if self._profile:
            return f"{base}-{self._profile}"
        return base

    def generate_unit(self, python_path: str = "", extra_args: str = "", env_vars: dict[str, str] | None = None) -> str:
        """Generate the systemd unit file content."""
        py = python_path or sys.executable
        exec_start = f"{py} -m predator gateway run"
        if self._profile:
            exec_start += f" --profile {self._profile}"
        if extra_args:
            exec_start += f" {extra_args}"

        extra_env = ""
        if env_vars:
            extra_env = "\n".join(f"Environment={k}={v}" for k, v in env_vars.items())

        return UNIT_TEMPLATE.format(
            profile_suffix=f" ({self._profile})" if self._profile else "",
            exec_start=exec_start,
            work_dir=os.path.expanduser("~"),
            state_dir=self._state_dir(),
            extra_env=extra_env,
        )

    def install(self, python_path: str = "", extra_args: str = "", env_vars: dict[str, str] | None = None) -> bool:
        """Install the systemd service."""
        os.makedirs(self._unit_dir, exist_ok=True)
        unit_content = self.generate_unit(python_path, extra_args, env_vars)

        with open(self._unit_path, "w") as f:
            f.write(unit_content)

        self._systemctl("daemon-reload")
        self._systemctl("enable", self._service_name)
        self._enable_linger()
        logger.info(f"Service installed: {self._service_name}")
        return True

    def uninstall(self) -> bool:
        """Remove the systemd service."""
        self._systemctl("stop", self._service_name)
        self._systemctl("disable", self._service_name)
        if os.path.isfile(self._unit_path):
            os.remove(self._unit_path)
        self._systemctl("daemon-reload")
        logger.info(f"Service uninstalled: {self._service_name}")
        return True

    def start(self) -> bool:
        return self._systemctl("start", self._service_name)

    def stop(self) -> bool:
        return self._systemctl("stop", self._service_name)

    def restart(self) -> bool:
        return self._systemctl("restart", self._service_name)

    def status(self) -> dict:
        """Get service status."""
        try:
            result = subprocess.run(
                ["systemctl", "--user", "status", self._service_name],
                capture_output=True, text=True, timeout=10,
            )
            active = "active (running)" in result.stdout
            return {
                "name": self._service_name,
                "active": active,
                "loaded": "loaded" in result.stdout,
                "output": result.stdout,
            }
        except Exception as e:
            return {"name": self._service_name, "active": False, "error": str(e)}

    def is_loaded(self) -> bool:
        return os.path.isfile(self._unit_path)

    def _systemctl(self, *args) -> bool:
        try:
            result = subprocess.run(
                ["systemctl", "--user", *args],
                capture_output=True, text=True, timeout=30,
            )
            return result.returncode == 0
        except Exception as e:
            logger.error(f"systemctl error: {e}")
            return False

    def _enable_linger(self) -> bool:
        """Enable lingering for the current user (persist services after logout)."""
        try:
            result = subprocess.run(
                ["loginctl", "enable-linger"],
                capture_output=True, text=True, timeout=10,
            )
            return result.returncode == 0
        except Exception:
            return False
