"""Cross-platform lifecycle management and graceful shutdown handling.

Captures OS signals (SIGINT, SIGTERM) across Windows and Unix platforms,
triggering registered teardown callbacks in reverse order of registration.
"""

from __future__ import annotations

import logging
import signal
import sys
from collections.abc import Callable
from types import FrameType

logger = logging.getLogger("glados.core.lifecycle")


class LifecycleManager:
    """Coordinates graceful process termination across operating systems."""

    def __init__(self) -> None:
        self._shutdown_callbacks: list[Callable[[], None]] = []
        self._is_shutting_down = False
        self._setup_signal_handlers()

    def register_shutdown_hook(self, callback: Callable[[], None]) -> None:
        """Register a callback function to be executed during graceful shutdown."""
        self._shutdown_callbacks.append(callback)

    def _setup_signal_handlers(self) -> None:
        """Attach signal handlers for process termination signals."""
        try:
            signal.signal(signal.SIGINT, self._handle_signal)
            signal.signal(signal.SIGTERM, self._handle_signal)
        except (ValueError, AttributeError) as exc:
            # Signal handling may fail if running in a non-main thread
            logger.debug("Failed to set up signal handlers: %s", exc)

    def _handle_signal(self, signum: int, _frame: FrameType | None) -> None:
        """Handle incoming termination signal."""
        sig_name = signal.Signals(signum).name if hasattr(signal, "Signals") else str(signum)
        logger.info("Received termination signal %s. Commencing graceful teardown...", sig_name)
        self.shutdown(exit_code=0)

    def shutdown(self, exit_code: int = 0) -> None:
        """Execute all registered shutdown hooks in reverse order and exit."""
        if self._is_shutting_down:
            return
        self._is_shutting_down = True

        for callback in reversed(self._shutdown_callbacks):
            try:
                callback()
            except Exception as exc:
                logger.error("Error executing shutdown hook %s: %s", callback.__name__, exc)

        if exit_code is not None:
            sys.exit(exit_code)


# Global lifecycle manager instance
lifecycle = LifecycleManager()
