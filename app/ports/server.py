"""Remote home server and homelab management port definitions (ZimaOS / CasaOS)."""

from __future__ import annotations

from typing import Any, Protocol, runtime_checkable


@runtime_checkable
class RemoteServerPort(Protocol):
    """Protocol for communicating with remote home servers and orchestrating containers."""

    def get_system_status(self) -> tuple[bool, dict[str, Any]]:
        """Retrieves CPU, RAM, disk, and container telemetry from the remote server."""
        ...

    def launch_app(self, app_name: str) -> tuple[bool, str]:
        """Launches or opens the web UI for a hosted container or application."""
        ...

    def list_apps(self) -> tuple[bool, list[str]]:
        """Lists active and installed applications or docker containers on the server."""
        ...
