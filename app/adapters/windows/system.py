"""Windows system facilities adapter implementing SystemPowerPort and TrashPort."""

from __future__ import annotations

import logging
import subprocess

from app.ports.system import SystemPowerPort, TrashPort

logger = logging.getLogger("glados.adapters.windows.system")


class WindowsSystemAdapter(SystemPowerPort, TrashPort):
    """Windows-specific system power, session lock, and recycle bin management."""

    def lock_workstation(self) -> bool:
        """Locks the active Windows workstation immediately."""
        try:
            import ctypes

            ctypes.windll.user32.LockWorkStation()
            return True
        except Exception as exc:
            logger.error("Failed to lock Windows workstation: %s", exc)
            return False

    def shutdown(self, delay_seconds: int = 0) -> bool:
        """Initiates Windows shutdown."""
        try:
            subprocess.run(["shutdown", "/s", "/t", str(delay_seconds)], check=True)
            return True
        except Exception as exc:
            logger.error("Failed to initiate Windows shutdown: %s", exc)
            return False

    def restart(self, delay_seconds: int = 0) -> bool:
        """Initiates Windows restart."""
        try:
            subprocess.run(["shutdown", "/r", "/t", str(delay_seconds)], check=True)
            return True
        except Exception as exc:
            logger.error("Failed to initiate Windows restart: %s", exc)
            return False

    def sleep(self) -> bool:
        """Suspends system into sleep state."""
        try:
            subprocess.run(["rundll32.exe", "powrprof.dll,SetSuspendState", "0,1,0"], check=True)
            return True
        except Exception as exc:
            logger.error("Failed to suspend Windows system: %s", exc)
            return False

    def empty_recycle_bin(self) -> tuple[bool, str]:
        """Empties the Windows Recycle Bin without prompt dialogs."""
        try:
            import ctypes

            # SHERB_NOCONFIRMATION (0x1) | SHERB_NOPROGRESSUI (0x2) | SHERB_NOSOUND (0x4) = 7
            res = ctypes.windll.shell32.SHEmptyRecycleBinW(None, None, 7)
            if res == 0:
                return True, "Recycle Bin emptied successfully."
            return False, f"Recycle Bin empty returned code: {res}"
        except Exception as exc:
            logger.error("Failed to empty Windows Recycle Bin: %s", exc)
            return False, f"Failed to empty Recycle Bin: {exc}"
