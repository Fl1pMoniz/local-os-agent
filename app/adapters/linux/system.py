"""Linux system facilities adapter implementing SystemPowerPort and TrashPort."""

from __future__ import annotations

import logging
import os
import shutil
import subprocess
from pathlib import Path

from app.ports.system import SystemPowerPort, TrashPort

logger = logging.getLogger("glados.adapters.linux.system")


def is_container_or_server() -> bool:
    """Detects whether code is executing within a Docker container, headless server, or ZimaOS."""
    if os.getenv("CONTAINER_MODE", "").lower() in ("true", "1", "yes"):
        return True
    if os.getenv("HEADLESS", "").lower() in ("true", "1", "yes"):
        return True
    if os.getenv("IS_ZIMAOS", "").lower() in ("true", "1", "yes"):
        return True
    if os.path.exists("/.dockerenv") or os.path.exists("/run/.containerenv"):
        return True
    if not os.getenv("DISPLAY") and not os.getenv("WAYLAND_DISPLAY"):
        return True
    return False


class LinuxSystemAdapter(SystemPowerPort, TrashPort):
    """Linux system power states, desktop session locking, and trash purge."""

    def lock_workstation(self) -> bool:
        """Locks the active desktop session via loginctl or xdg-screensaver."""
        if is_container_or_server():
            logger.info(
                "LinuxSystemAdapter: lock_workstation safely bypassed in headless/server environment."
            )
            return True

        if shutil.which("loginctl"):
            try:
                subprocess.run(["loginctl", "lock-session"], check=True, timeout=2.0)
                return True
            except Exception as exc:
                logger.debug("loginctl lock-session failed: %s", exc)

        if shutil.which("xdg-screensaver"):
            try:
                subprocess.run(["xdg-screensaver", "lock"], check=True, timeout=2.0)
                return True
            except Exception as exc:
                logger.debug("xdg-screensaver lock failed: %s", exc)

        return False

    def shutdown(self, delay_seconds: int = 0) -> bool:
        """Initiates system shutdown via systemctl."""
        if is_container_or_server():
            logger.warning("LinuxSystemAdapter: shutdown rejected in headless/server environment.")
            return False
        try:
            if delay_seconds > 0 and shutil.which("shutdown"):
                mins = max(1, delay_seconds // 60)
                subprocess.run(["shutdown", "-h", f"+{mins}"], check=True)
            else:
                subprocess.run(["systemctl", "poweroff"], check=True)
            return True
        except Exception as exc:
            logger.error("Failed to shutdown Linux system: %s", exc)
            return False

    def restart(self, delay_seconds: int = 0) -> bool:
        """Initiates system restart via systemctl."""
        if is_container_or_server():
            logger.warning("LinuxSystemAdapter: restart rejected in headless/server environment.")
            return False
        try:
            subprocess.run(["systemctl", "reboot"], check=True)
            return True
        except Exception as exc:
            logger.error("Failed to reboot Linux system: %s", exc)
            return False

    def sleep(self) -> bool:
        """Suspends system state via systemctl."""
        if is_container_or_server():
            logger.warning(
                "LinuxSystemAdapter: sleep/suspend rejected in headless/server environment."
            )
            return False
        try:
            subprocess.run(["systemctl", "suspend"], check=True)
            return True
        except Exception as exc:
            logger.error("Failed to suspend Linux system: %s", exc)
            return False

    def empty_recycle_bin(self) -> tuple[bool, str]:
        """Purges items from XDG trash via gio or filesystem removal."""
        if shutil.which("gio"):
            try:
                subprocess.run(["gio", "trash", "--empty"], check=True, timeout=5.0)
                return True, "Linux trash emptied successfully."
            except Exception as exc:
                logger.debug("gio trash --empty failed: %s", exc)

        # Fallback to direct XDG trash folder clearing
        trash_dir = Path(os.path.expanduser("~/.local/share/Trash"))
        if trash_dir.exists():
            try:
                for sub in ("files", "info"):
                    p = trash_dir / sub
                    if p.exists():
                        for item in p.iterdir():
                            if item.is_dir():
                                shutil.rmtree(item, ignore_errors=True)
                            else:
                                item.unlink(missing_ok=True)
                return True, "Purged ~/.local/share/Trash successfully."
            except Exception as exc:
                return False, f"Failed to purge trash files: {exc}"

        return True, "No trash items to purge."
