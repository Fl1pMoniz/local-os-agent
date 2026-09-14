"""Cross-platform ZimaOS / CasaOS client implementing RemoteServerPort."""

from __future__ import annotations

from typing import Any

from app.ports.server import RemoteServerPort


class ZimaOsHttpAdapter(RemoteServerPort):
    """Communicates with remote ZimaOS / CasaOS homelab server via REST endpoints."""

    def get_system_status(self) -> tuple[bool, dict[str, Any]]:
        """Retrieves system status and hardware metrics from ZimaOS."""
        from tools import zimaos

        success, output = zimaos.get_zimaos_status()
        if not success:
            return False, {"error": output}

        # Attempt to extract parsed metrics dictionary
        return True, {"raw_status": output}

    def launch_app(self, app_name: str) -> tuple[bool, str]:
        """Commands remote launch or opens browser UI for a ZimaOS app."""
        from tools import zimaos

        return zimaos.launch_zimaos_app(app_name)

    def list_apps(self) -> tuple[bool, list[str]]:
        """Lists active apps or containers on the remote host."""
        from tools import zimaos

        success, output = zimaos.list_zimaos_apps()
        if not success:
            return False, []

        lines = [line.strip() for line in output.splitlines() if line.strip()]
        return True, lines
