"""Operating system level facilities port definitions."""

from __future__ import annotations

from typing import Protocol, runtime_checkable


@runtime_checkable
class SystemPowerPort(Protocol):
    """Protocol for system power states and session locking."""

    def lock_workstation(self) -> bool:
        """Locks the active user desktop session."""
        ...

    def shutdown(self, delay_seconds: int = 0) -> bool:
        """Initiates an orderly system shutdown."""
        ...

    def restart(self, delay_seconds: int = 0) -> bool:
        """Initiates an orderly system restart."""
        ...

    def sleep(self) -> bool:
        """Suspends system to RAM or low-power state."""
        ...


@runtime_checkable
class TrashPort(Protocol):
    """Protocol for recycling bin and trash purge operations."""

    def empty_recycle_bin(self) -> tuple[bool, str]:
        """Purges deleted items from system recycle bin or user trash."""
        ...


@runtime_checkable
class WindowInspectionPort(Protocol):
    """Protocol for inspecting the active desktop window."""

    def get_active_window_title(self) -> str:
        """Returns the title string of the currently focused foreground window."""
        ...


@runtime_checkable
class InstanceLockPort(Protocol):
    """Protocol for enforcing single-instance application execution."""

    def acquire(self) -> bool:
        """Attempts to acquire the instance lock. Returns True if successful."""
        ...

    def release(self) -> None:
        """Releases the instance lock upon clean shutdown."""
        ...

    def is_locked(self) -> bool:
        """Checks if another instance currently holds the lock."""
        ...
