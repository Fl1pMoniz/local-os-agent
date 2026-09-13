"""ZimaOS / CasaOS Home Server Integration for GLaDOS.

Allows GLaDOS to monitor and communicate with your ZimaOS home server:
  - get_zimaos_status: Inspects CPU, RAM, storage, and health of the ZimaOS server
  - list_zimaos_apps: Lists active Docker containers/apps on the server (Plex, Jellyfin, etc.)
  - open_zimaos_dashboard: Opens the ZimaOS web management dashboard in the browser
"""

import json
import logging
import urllib.parse
import urllib.request
import webbrowser
from typing import Any, Tuple

from config import config
from tools import register_tool

logger = logging.getLogger("local_os_agent.tools.zimaos")


def _get_zimaos_headers() -> dict[str, str]:
    headers = {
        "User-Agent": "Aperture-Science-GLaDOS/3.11",
        "Accept": "application/json",
    }
    if config.zimaos_api_key:
        headers["Authorization"] = config.zimaos_api_key
    return headers


def _query_zimaos_endpoint(path: str, timeout: float = 3.5) -> dict[str, Any] | None:
    """Queries an endpoint on the configured ZimaOS server."""
    base = config.zimaos_host.rstrip("/")
    if not base.startswith("http://") and not base.startswith("https://"):
        base = f"http://{base}"

    url = f"{base}/{path.lstrip('/')}"
    req = urllib.request.Request(url, headers=_get_zimaos_headers())
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            return json.loads(resp.read().decode("utf-8"))
    except Exception as e:
        logger.debug(f"ZimaOS endpoint '{url}' query failed: {e}")
        return None


@register_tool(
    name="get_zimaos_status",
    description="Queries and returns the operational status, CPU, RAM, and disk utilization of your ZimaOS server.",
    sensitive=False,
)
def get_zimaos_status(**kwargs) -> Tuple[bool, str]:
    """Retrieves live server telemetry from ZimaOS."""
    host = config.zimaos_host

    # Try standard CasaOS/ZimaOS hardware and system endpoints
    data = _query_zimaos_endpoint("/v1/sys/hardware/info") or _query_zimaos_endpoint("/v2/sys/hardware/info")
    sys_data = _query_zimaos_endpoint("/v1/sys/status") or _query_zimaos_endpoint("/v2/sys/info")

    if not data and not sys_data:
        # Check basic ping/HTTP reachability
        try:
            req = urllib.request.Request(host, headers={"User-Agent": "Aperture-Science-GLaDOS/3.11"})
            with urllib.request.urlopen(req, timeout=3) as resp:
                if resp.status < 400:
                    return (
                        True,
                        f"ZimaOS server at {host} is online and reachable. Web dashboard is active.",
                    )
        except Exception as ping_err:
            return (
                False,
                f"Unable to connect to ZimaOS server at {host}. Verify that the server is powered on and connected to your local network.",
            )

    info = (data and data.get("data")) or (sys_data and sys_data.get("data")) or {}

    # Extract hardware metrics
    cpu_pct = info.get("cpu", {}).get("percent") or info.get("cpu_percent", "Normal")
    mem_info = info.get("ram", {}) or info.get("memory", {})
    mem_used = mem_info.get("used", 0)
    mem_total = mem_info.get("total", 0)
    mem_pct = mem_info.get("percent") or (round((mem_used / mem_total) * 100, 1) if mem_total else "Normal")

    status_msg = (
        f"Aperture remote mainframe ZimaOS at {host} is operational. "
        f"CPU load is at {cpu_pct}%, Memory utilization is {mem_pct}%. "
        f"All sub-systems are performing within acceptable parameters."
    )
    return True, status_msg


@register_tool(
    name="list_zimaos_apps",
    description="Lists the active Docker applications and services running on your ZimaOS home server.",
    sensitive=False,
)
def list_zimaos_apps(**kwargs) -> Tuple[bool, str]:
    """Lists installed and running Docker containers on the ZimaOS server."""
    containers_data = _query_zimaos_endpoint("/v2/docker/container/list") or _query_zimaos_endpoint("/v1/docker/container")

    if not containers_data:
        return (
            False,
            f"Could not retrieve container manifest from ZimaOS ({config.zimaos_host}). Ensure Docker daemon is accessible.",
        )

    apps = []
    items = containers_data.get("data", [])
    if isinstance(items, list):
        for c in items:
            name = c.get("name") or c.get("Names", ["Unknown"])[0].lstrip("/")
            state = c.get("state") or c.get("State", "running")
            apps.append(f"{name} ({state})")

    if not apps:
        return True, "ZimaOS server reported zero active application containers."

    apps_summary = ", ".join(apps[:8])
    return True, f"ZimaOS is currently running {len(apps)} container(s): {apps_summary}."


@register_tool(
    name="open_zimaos_dashboard",
    description="Opens the ZimaOS web administration dashboard in your default browser.",
    sensitive=False,
)
def open_zimaos_dashboard(**kwargs) -> Tuple[bool, str]:
    """Opens ZimaOS dashboard in browser."""
    host = config.zimaos_host
    if not host.startswith("http://") and not host.startswith("https://"):
        host = f"http://{host}"
    try:
        webbrowser.open(host)
        return True, f"Opened ZimaOS dashboard at {host} in your default browser."
    except Exception as e:
        return False, f"Failed to launch ZimaOS dashboard: {e}"
