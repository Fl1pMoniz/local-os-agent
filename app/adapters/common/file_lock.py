"""Cross-platform single-instance locking using portalocker.

Provides file-based mutual exclusion compatible across Windows, Linux, macOS,
and container environments, replacing platform-specific kernel mutexes.
"""

from __future__ import annotations

import logging
from pathlib import Path
from typing import IO, Any

import portalocker

from app.ports.system import InstanceLockPort

logger = logging.getLogger("glados.adapters.file_lock")


class FileInstanceLock(InstanceLockPort):
    """File lock based instance limiter preventing concurrent GLaDOS processes."""

    def __init__(self, lock_path: Path | str | None = None) -> None:
        if lock_path is None:
            from app.core.config import settings

            self._lock_path = settings.lock_file
        else:
            self._lock_path = Path(lock_path)

        self._lock_file: IO[Any] | None = None
        self._acquired = False

    def acquire(self) -> bool:
        """Attempts non-blocking acquisition of the file lock."""
        if self._acquired:
            return True

        try:
            self._lock_path.parent.mkdir(parents=True, exist_ok=True)
            self._lock_file = open(self._lock_path, "a+")
            portalocker.lock(self._lock_file, portalocker.LOCK_EX | portalocker.LOCK_NB)
            self._acquired = True
            logger.debug("Successfully acquired process instance lock on %s", self._lock_path)
            return True
        except (portalocker.exceptions.LockException, OSError) as exc:
            logger.warning("Failed to acquire instance lock on %s: %s", self._lock_path, exc)
            if self._lock_file:
                try:
                    self._lock_file.close()
                except Exception:
                    pass
                self._lock_file = None
            self._acquired = False
            return False

    def release(self) -> None:
        """Releases the file lock and closes file handle."""
        if not self._acquired or not self._lock_file:
            return

        try:
            portalocker.unlock(self._lock_file)
            self._lock_file.close()
            logger.debug("Released process instance lock on %s", self._lock_path)
        except Exception as exc:
            logger.error("Error releasing instance lock on %s: %s", self._lock_path, exc)
        finally:
            self._lock_file = None
            self._acquired = False

    def is_locked(self) -> bool:
        """Checks whether the lock is currently held by this instance."""
        return self._acquired
