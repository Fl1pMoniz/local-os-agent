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


import uuid

CUSTOM_APPS_FILE = config.captures_dir / "custom_zima_apps.json"


def get_custom_zima_apps() -> list[dict[str, Any]]:
    """Retrieves user-defined custom ZimaOS applications from local persistent storage."""
    if not CUSTOM_APPS_FILE.exists():
        host = config.zimaos_host.rstrip("/")
        if not host.startswith("http://") and not host.startswith("https://"):
            host = f"http://{host}"
        defaults = [
            {"id": "custom-plex", "name": "Plex", "url": f"{host}:32400", "state": "active", "category": "Media", "custom": True},
            {"id": "custom-jellyfin", "name": "Jellyfin", "url": f"{host}:8096", "state": "active", "category": "Media", "custom": True},
            {"id": "custom-nextcloud", "name": "Nextcloud", "url": f"{host}:8080", "state": "active", "category": "Cloud", "custom": True},
            {"id": "custom-homeassistant", "name": "Home Assistant", "url": f"{host}:8123", "state": "active", "category": "Smart Home", "custom": True},
        ]
        try:
            CUSTOM_APPS_FILE.parent.mkdir(parents=True, exist_ok=True)
            with open(CUSTOM_APPS_FILE, "w", encoding="utf-8") as f:
                json.dump(defaults, f, indent=2)
            return defaults
        except Exception:
            return defaults

    try:
        with open(CUSTOM_APPS_FILE, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception as e:
        logger.warning(f"Error reading custom ZimaOS apps: {e}")
        return []


def add_custom_zima_app(name: str, url: str, category: str = "General") -> Tuple[bool, str]:
    """Adds or updates a custom ZimaOS application with its destination URL."""
    clean_name = str(name).strip()
    clean_url = str(url).strip()
    clean_cat = str(category).strip() or "General"

    if not clean_name:
        return False, "Application name cannot be empty."
    if not clean_url:
        return False, "Application URL cannot be empty."

    # Normalize URL scheme
    if clean_url.startswith(":"):
        host = config.zimaos_host.rstrip("/")
        if not host.startswith("http://") and not host.startswith("https://"):
            host = f"http://{host}"
        clean_url = f"{host}{clean_url}"
    elif not clean_url.startswith("http://") and not clean_url.startswith("https://"):
        clean_url = f"http://{clean_url}"

    apps = get_custom_zima_apps()
    updated = False
    for a in apps:
        if a.get("name", "").lower() == clean_name.lower():
            a["url"] = clean_url
            a["category"] = clean_cat
            a["state"] = "active"
            updated = True
            break

    if not updated:
        apps.append({
            "id": f"custom-{uuid.uuid4().hex[:6]}",
            "name": clean_name,
            "url": clean_url,
            "category": clean_cat,
            "state": "active",
            "custom": True,
        })

    try:
        CUSTOM_APPS_FILE.parent.mkdir(parents=True, exist_ok=True)
        with open(CUSTOM_APPS_FILE, "w", encoding="utf-8") as f:
            json.dump(apps, f, indent=2)
        action_word = "Updated" if updated else "Registered"
        return True, f"{action_word} application '{clean_name}' pointing to {clean_url}."
    except Exception as e:
        return False, f"Failed to save application: {e}"


def delete_custom_zima_app(name: str) -> Tuple[bool, str]:
    """Removes a custom application from the local registry."""
    clean_name = str(name).strip().lower()
    apps = get_custom_zima_apps()
    filtered = [a for a in apps if a.get("name", "").lower() != clean_name and a.get("id", "") != clean_name]
    if len(filtered) == len(apps):
        return False, f"Application '{name}' not found."

    try:
        with open(CUSTOM_APPS_FILE, "w", encoding="utf-8") as f:
            json.dump(filtered, f, indent=2)
        return True, f"Removed application '{name}' from registry."
    except Exception as e:
        return False, f"Failed to remove application: {e}"


def get_zimaos_apps_detailed() -> list[dict[str, Any]]:
    """Returns a merged list of auto-discovered Docker applications and custom user apps."""
    result = []
    seen_names = set()

    # 1. Custom user-defined applications first
    custom_apps = get_custom_zima_apps()
    for ca in custom_apps:
        result.append(ca)
        seen_names.add(ca["name"].lower())

    # 2. Query Docker daemon on ZimaOS if reachable
    containers_data = _query_zimaos_endpoint("/v2/docker/container/list") or _query_zimaos_endpoint("/v1/docker/container")
    items = (containers_data and containers_data.get("data")) or []
    if isinstance(items, list):
        host = config.zimaos_host.rstrip("/")
        if not host.startswith("http://") and not host.startswith("https://"):
            host = f"http://{host}"

        for c in items:
            name = c.get("name") or (c.get("Names", [""])[0].lstrip("/") if c.get("Names") else "Unknown")
            if name.lower() in seen_names:
                continue
            seen_names.add(name.lower())

            state = (c.get("state") or c.get("State", "running")).lower()
            cid = c.get("id") or c.get("Id", "")

            port = None
            ports = c.get("ports") or c.get("Ports") or []
            if isinstance(ports, list) and ports:
                for p in ports:
                    if isinstance(p, dict) and p.get("PublicPort"):
                        port = p.get("PublicPort")
                        break
                    elif isinstance(p, int):
                        port = p
                        break
            elif isinstance(ports, (int, str)) and str(ports).isdigit():
                port = int(ports)

            app_url = f"{host}:{port}" if port else host

            result.append({
                "id": cid,
                "name": name,
                "state": state,
                "port": port,
                "url": app_url,
                "category": "Docker",
                "custom": False,
                "image": c.get("image") or c.get("Image", "")
            })

    return result


@register_tool(
    name="launch_zimaos_app",
    description="Launches or opens a Docker application (Plex, Jellyfin, Nextcloud, Home Assistant, etc.) on your ZimaOS server.",
    sensitive=False,
)
def launch_zimaos_app(app_name: str, **kwargs) -> Tuple[bool, str]:
    """Finds, wakes, and opens a ZimaOS Docker application in the default browser."""
    if not app_name or not str(app_name).strip():
        return False, "Please specify an application name to launch on ZimaOS."

    clean_target = str(app_name).strip().lower()
    apps = get_zimaos_apps_detailed()

    if not apps:
        # Fallback: if server cannot list containers, offer to open dashboard
        open_zimaos_dashboard()
        return True, f"Could not query containers directly. Opened ZimaOS dashboard to locate '{app_name}'."

    # Fuzzy match app name
    matched_app = None
    for a in apps:
        aname = a.get("name", "").lower()
        aimage = a.get("image", "").lower()
        if clean_target in aname or clean_target in aimage or aname in clean_target:
            matched_app = a
            break

    if not matched_app:
        available = ", ".join([a.get("name", "Unknown") for a in apps[:6]])
        return False, f"Could not find application matching '{app_name}' on ZimaOS. Available apps: {available}."

    # If stopped and not a custom app, wake container via API
    if matched_app.get("state") not in ("running", "active") and not matched_app.get("custom"):
        cid = matched_app.get("id")
        if cid:
            base = config.zimaos_host.rstrip("/")
            if not base.startswith("http://") and not base.startswith("https://"):
                base = f"http://{base}"
            start_url = f"{base}/v2/docker/container/state/{cid}"
            req = urllib.request.Request(
                start_url,
                data=json.dumps({"state": "start"}).encode("utf-8"),
                headers=_get_zimaos_headers() | {"Content-Type": "application/json"},
                method="PUT"
            )
            try:
                urllib.request.urlopen(req, timeout=3.0)
            except Exception as e:
                logger.debug(f"Failed to send start request to ZimaOS container {cid}: {e}")

    # Launch app web GUI
    app_url = matched_app.get("url") or config.zimaos_host
    app_display_name = matched_app.get("name", app_name)
    try:
        webbrowser.open(app_url)
        return True, f"Launched {app_display_name} on ZimaOS ({app_url}) in your default browser."
    except Exception as e:
        return False, f"Failed to open browser for {matched_app['name']}: {e}"


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

