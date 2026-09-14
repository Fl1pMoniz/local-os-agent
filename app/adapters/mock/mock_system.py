"""Mock system facilities implementing SystemPowerPort, TrashPort, and WindowInspectionPort."""

from __future__ import annotations

import logging

from app.ports.system import SystemPowerPort, TrashPort, WindowInspectionPort

logger = logging.getLogger("glados.adapters.mock.system")


class MockSystemAdapter(SystemPowerPort, TrashPort, WindowInspectionPort):
    """Mock operating system facilities for testing and headless execution."""

    def lock_workstation(self) -> bool:
        """Simulates workstation locking."""
        logger.debug("MockSystemAdapter: lock_workstation called")
        return True

    def shutdown(self, delay_seconds: int = 0) -> bool:
        """Simulates system shutdown."""
        logger.debug("MockSystemAdapter: shutdown called (delay=%s)", delay_seconds)
        return True

    def restart(self, delay_seconds: int = 0) -> bool:
        """Simulates system reboot."""
        logger.debug("MockSystemAdapter: restart called (delay=%s)", delay_seconds)
        return True

    def sleep(self) -> bool:
        """Simulates system suspend."""
        logger.debug("MockSystemAdapter: sleep called")
        return True

    def empty_recycle_bin(self) -> tuple[bool, str]:
        """Simulates recycle bin purge."""
        logger.debug("MockSystemAdapter: empty_recycle_bin called")
        return True, "Simulated recycle bin emptied successfully."

    def get_active_window_title(self) -> str:
        """Returns mock window title."""
        return "Headless Server Terminal"
