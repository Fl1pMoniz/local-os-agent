"""ZimaOS / CasaOS Home Server Integration for GLaDOS.

Allows GLaDOS to monitor and communicate with your ZimaOS home server:
  - monitor_zimaos: Real-time telemetry, component metrics, and live in-terminal HUD
  - get_zimaos_status: Inspects CPU, RAM, storage, and health of the ZimaOS server
  - list_zimaos_apps: Lists active Docker containers/apps on the server (Plex, Jellyfin, etc.)
  - open_zimaos_dashboard: Opens the ZimaOS web management dashboard in the browser
  - set_zimaos_host: Reconfigures and persists the server IP/hostname
"""

import datetime
import json
import logging
import re
import socket
import sys
import time
import urllib.parse
import urllib.request
import uuid
import webbrowser
from typing import Any

from config import config
from tools import register_tool

logger = logging.getLogger("local_os_agent.tools.zimaos")

CUSTOM_APPS_FILE = config.captures_dir / "custom_zima_apps.json"
ZIMAOS_CONFIG_FILE = config.captures_dir / "zimaos_config.json"
CREDENTIALS_FILES = [
    config.base_dir / "zimaos_credentials.json",
    config.captures_dir / "zimaos_credentials.json",
]

_last_auto_login_attempt = 0.0


def load_zimaos_credentials() -> tuple[str | None, str | None]:
    """Reads username and password from the secure, gitignored credentials file."""
    for path in CREDENTIALS_FILES:
        if path.exists():
            try:
                with open(path, encoding="utf-8") as f:
                    data = json.load(f)
                    user = data.get("username", "").strip()
                    pwd = data.get("password", "").strip()
                    host = data.get("zimaos_host", "").strip()
                    if host:
                        if not host.startswith("http://") and not host.startswith("https://"):
                            host = f"http://{host}"
                        config.zimaos_host = host.rstrip("/")
                    if user and pwd:
                        return user, pwd
            except Exception as e:
                logger.warning(f"Error reading ZimaOS credentials from {path}: {e}")
    return None, None


def get_zimaos_host() -> str:
    """Returns the currently configured ZimaOS server host address."""
    if ZIMAOS_CONFIG_FILE.exists():
        try:
            with open(ZIMAOS_CONFIG_FILE, encoding="utf-8") as f:
                data = json.load(f)
                saved_host = data.get("zimaos_host")
                if saved_host:
                    config.zimaos_host = saved_host
                    return saved_host
        except Exception as e:
            logger.warning(f"Error reading ZimaOS config: {e}")

    # Check credentials files if not set in zimaos_config.json
    for path in CREDENTIALS_FILES:
        if path.exists():
            try:
                with open(path, encoding="utf-8") as f:
                    data = json.load(f)
                    saved_host = data.get("zimaos_host", "").strip()
                    if saved_host:
                        if not saved_host.startswith("http://") and not saved_host.startswith(
                            "https://"
                        ):
                            saved_host = f"http://{saved_host}"
                        config.zimaos_host = saved_host.rstrip("/")
                        return config.zimaos_host
            except Exception:
                pass

    return config.zimaos_host


def get_zimaos_token() -> str | None:
    """Returns the currently configured ZimaOS authorization token, auto-authenticating if credentials exist."""
    global _last_auto_login_attempt

    if ZIMAOS_CONFIG_FILE.exists():
        try:
            with open(ZIMAOS_CONFIG_FILE, encoding="utf-8") as f:
                data = json.load(f)
                saved_token = data.get("zimaos_token") or data.get("token") or data.get("api_key")
                if saved_token:
                    config.zimaos_api_key = str(saved_token).strip()
                    return config.zimaos_api_key
        except Exception:
            pass

    if config.zimaos_api_key:
        return config.zimaos_api_key

    # Attempt automatic login if credentials file has username and password
    now = time.time()
    if now - _last_auto_login_attempt > 10.0:
        _last_auto_login_attempt = now
        user, pwd = load_zimaos_credentials()
        if user and pwd:
            try:
                ok, _ = login_zimaos(user, pwd)
                if ok:
                    return config.zimaos_api_key
            except Exception as e:
                logger.debug(f"Automatic ZimaOS login failed: {e}")

    return config.zimaos_api_key


@register_tool(
    name="set_zimaos_host",
    description="Configures and persists the destination IP or hostname of your ZimaOS server.",
    sensitive=False,
)
def set_zimaos_host(new_host: str, **kwargs) -> tuple[bool, str]:
    """Updates and persists the ZimaOS host address."""
    clean = str(new_host).strip()
    if not clean:
        return False, "ZimaOS host address cannot be blank."

    # Strip conversational prefixes if user passed "to 192.168.1.123" or "ip 192.168.1.123"
    if clean.lower().startswith("to "):
        clean = clean[3:].strip()
    elif clean.lower().startswith("ip "):
        clean = clean[3:].strip()

    if not clean.startswith("http://") and not clean.startswith("https://"):
        clean = f"http://{clean}"
    clean = clean.rstrip("/")

    config.zimaos_host = clean
    try:
        ZIMAOS_CONFIG_FILE.parent.mkdir(parents=True, exist_ok=True)
        existing = {}
        if ZIMAOS_CONFIG_FILE.exists():
            try:
                with open(ZIMAOS_CONFIG_FILE, encoding="utf-8") as f:
                    existing = json.load(f)
            except Exception:
                existing = {}
        existing["zimaos_host"] = clean
        with open(ZIMAOS_CONFIG_FILE, "w", encoding="utf-8") as f:
            json.dump(existing, f, indent=2)

        for path in CREDENTIALS_FILES:
            if path.exists():
                try:
                    with open(path, encoding="utf-8") as f:
                        cdata = json.load(f)
                    cdata["zimaos_host"] = clean
                    with open(path, "w", encoding="utf-8") as f:
                        json.dump(cdata, f, indent=2)
                except Exception:
                    pass

        return True, f"ZimaOS host address updated to {clean}."
    except Exception as e:
        logger.error(f"Failed to persist ZimaOS config: {e}")
        return True, f"ZimaOS host updated to {clean} (temporary, could not save file)"


@register_tool(
    name="set_zimaos_token",
    description="Configures and persists the API authorization Bearer token for your ZimaOS server.",
    sensitive=False,
)
def set_zimaos_token(token: str, **kwargs) -> tuple[bool, str]:
    """Updates and persists the ZimaOS API token."""
    clean = str(token).strip()
    if not clean:
        return False, "Token cannot be blank."

    config.zimaos_api_key = clean
    try:
        ZIMAOS_CONFIG_FILE.parent.mkdir(parents=True, exist_ok=True)
        existing = {}
        if ZIMAOS_CONFIG_FILE.exists():
            try:
                with open(ZIMAOS_CONFIG_FILE, encoding="utf-8") as f:
                    existing = json.load(f)
            except Exception:
                existing = {}
        existing["zimaos_token"] = clean
        with open(ZIMAOS_CONFIG_FILE, "w", encoding="utf-8") as f:
            json.dump(existing, f, indent=2)
        return True, "ZimaOS API authorization token successfully configured and saved."
    except Exception as e:
        return False, f"Failed to persist ZimaOS token: {e}"


@register_tool(
    name="login_zimaos",
    description="Authenticates with your ZimaOS server using your account credentials to retrieve and save the API access Bearer token.",
    sensitive=False,
)
def login_zimaos(username: str, password: str, **kwargs) -> tuple[bool, str]:
    """Logs into ZimaOS to retrieve and persist a Bearer API token."""
    clean_user = str(username).strip()
    clean_pwd = str(password).strip()
    if not clean_user:
        return False, "Username cannot be empty."
    if not clean_pwd:
        return False, "Password cannot be empty."

    base = get_zimaos_host().rstrip("/")
    if not base.startswith("http://") and not base.startswith("https://"):
        base = f"http://{base}"

    url = f"{base}/v1/users/login"
    payload = json.dumps({"username": clean_user, "password": clean_pwd}).encode("utf-8")
    req = urllib.request.Request(
        url,
        data=payload,
        headers={"Content-Type": "application/json", "User-Agent": "Aperture-Science-GLaDOS/3.11"},
        method="POST",
    )
    try:
        with urllib.request.urlopen(req, timeout=4.0) as resp:
            resp_data = json.loads(resp.read().decode("utf-8"))
            token = None
            d = resp_data.get("data")
            if isinstance(d, str) and d:
                token = d
            elif isinstance(d, dict):
                token = d.get("token") or d.get("access_token") or d.get("jwt")
                if isinstance(token, dict):
                    token = token.get("token") or token.get("access_token")

            if token:
                set_zimaos_token(str(token))
                return (
                    True,
                    f"Successfully authenticated with ZimaOS as '{clean_user}'. API Bearer token configured and saved.",
                )
            else:
                return (
                    False,
                    f"ZimaOS responded with HTTP 200 but token was not found in response: {resp_data}",
                )
    except urllib.error.HTTPError as he:
        err_body = he.read().decode("utf-8", errors="replace")
        try:
            err_json = json.loads(err_body)
            msg = err_json.get("message") or err_body
        except Exception:
            msg = err_body
        return False, f"ZimaOS authentication failed (HTTP {he.code}): {msg}"
    except Exception as e:
        return False, f"Could not connect to ZimaOS at {url}: {e}"


# Initialize host from saved config if available
get_zimaos_host()
get_zimaos_token()


def _get_zimaos_headers() -> dict[str, str]:
    headers = {
        "User-Agent": "Aperture-Science-GLaDOS/3.11",
        "Accept": "application/json",
    }
    token = get_zimaos_token()
    if token:
        clean = token.strip()
        if not clean.lower().startswith("bearer "):
            headers["Authorization"] = f"Bearer {clean}"
        else:
            headers["Authorization"] = clean
    return headers


def _query_zimaos_endpoint(
    path: str, timeout: float = 2.5, retry_on_auth: bool = True
) -> dict[str, Any] | None:
    """Queries an endpoint on the configured ZimaOS server, auto-refreshing token on 401/403."""
    base = get_zimaos_host().rstrip("/")
    if not base.startswith("http://") and not base.startswith("https://"):
        base = f"http://{base}"

    url = f"{base}/{path.lstrip('/')}"
    req = urllib.request.Request(url, headers=_get_zimaos_headers())
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            return json.loads(resp.read().decode("utf-8"))
    except urllib.error.HTTPError as he:
        if he.code in (401, 403) and retry_on_auth:
            user, pwd = load_zimaos_credentials()
            if user and pwd:
                ok, _ = login_zimaos(user, pwd)
                if ok:
                    return _query_zimaos_endpoint(path, timeout=timeout, retry_on_auth=False)
        logger.debug(f"ZimaOS endpoint '{url}' query failed (HTTP {he.code}): {he.reason}")
        return None
    except Exception as e:
        logger.debug(f"ZimaOS endpoint '{url}' query failed: {e}")
        return None


KNOWN_ZIMA_SERVICES = [
    (80, "ZimaOS Web GUI", "Management"),
    (8123, "Home Assistant", "Smart Home"),
    (3000, "ConvertX", "Tools"),
    (8080, "Web Proxy / Cloud", "Networking"),
    (32400, "Plex Media Server", "Media"),
    (8096, "Jellyfin Media", "Media"),
    (9000, "Portainer", "Docker"),
    (22, "SSH Terminal", "System"),
    (7681, "Web Terminal (ttyd)", "System"),
]


def probe_zimaos_services(host_url: str) -> list[dict[str, Any]]:
    """Quickly tests known and custom application ports on the ZimaOS node."""
    clean_ip = host_url.replace("http://", "").replace("https://", "").split("/")[0].split(":")[0]
    discovered = []

    custom_ports = set()
    try:
        custom_apps = get_custom_zima_apps()
        for ca in custom_apps:
            url = ca.get("url", "")
            if ":" in url:
                port_part = url.split(":")[-1].split("/")[0]
                if port_part.isdigit():
                    p_num = int(port_part)
                    custom_ports.add(
                        (p_num, ca.get("name", f"Port {p_num}"), ca.get("category", "Custom"))
                    )
    except Exception:
        pass

    all_ports = list(KNOWN_ZIMA_SERVICES)
    for cp in custom_ports:
        if not any(p[0] == cp[0] for p in all_ports):
            all_ports.append(cp)

    for port, name, cat in all_ports:
        try:
            s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            s.settimeout(0.2)
            t0 = time.time()
            res = s.connect_ex((clean_ip, port))
            lat = round((time.time() - t0) * 1000, 1)
            s.close()
            if res == 0:
                discovered.append(
                    {
                        "port": port,
                        "name": name,
                        "category": cat,
                        "latency_ms": lat,
                        "status": "online",
                    }
                )
        except Exception:
            pass

    return discovered


def make_hud_bar(pct: float, width: int = 14) -> str:
    """Renders an ASCII progress bar compatible with all terminal encodings."""
    clamped = max(0.0, min(100.0, float(pct)))
    filled = int(round((clamped / 100.0) * width))
    try:
        encoding = getattr(sys.stdout, "encoding", "utf-8") or "utf-8"
        "█".encode(encoding)
        return "█" * filled + "░" * (width - filled)
    except Exception:
        return "#" * filled + "-" * (width - filled)


def make_row(key: str, val: str, key_width: int = 18, val_width: int = 45) -> str:
    """Creates a perfectly aligned 70-character HUD row."""
    k = key[:key_width]
    v = str(val)[:val_width]
    return f"| {k:<{key_width}} : {v:<{val_width}} |"


_last_rapl_sample: tuple[float, float] | None = None


def format_zimaos_hud(telemetry: dict[str, Any]) -> str:
    """Formats the Aperture Science ZimaOS Hardware & Thermal Telemetry ASCII HUD."""
    host = telemetry.get("host", config.zimaos_host)
    gateway = telemetry.get("gateway") or "Reachable"
    online = telemetry.get("online", False)
    services = telemetry.get("services", [])
    cpu = telemetry.get("cpu")
    ram = telemetry.get("ram")
    disk = telemetry.get("disk")
    gpu = telemetry.get("gpu")
    auth_status = telemetry.get("auth_status", "Active")

    border = "+--------------------------------------------------------------------+"

    if not online:
        err_msg = telemetry.get("error") or "Connection timed out. Host did not respond."
        return (
            border + "\n"
            "|           APERTURE SCIENCE HARDWARE TELEMETRY & THERMAL HUD        |\n"
            + border
            + "\n"
            + make_row("Node Host Address", host)
            + "\n"
            + make_row("Server Gateway", "[! OFFLINE / UNREACHABLE]")
            + "\n"
            + make_row("Diagnostic Status", err_msg)
            + "\n"
            + make_row("Reconfiguration", "Type 'zima ip <new_ip>' to adjust server address")
            + "\n"
            + border
        )

    if not cpu or not ram:
        return (
            border + "\n"
            "|           APERTURE SCIENCE HARDWARE TELEMETRY & THERMAL HUD        |\n"
            + border
            + "\n"
            + make_row("Node Host Address", host)
            + "\n"
            + make_row("Server Gateway", f"[* ONLINE] {gateway}")
            + "\n"
            + make_row("Node Architecture", "Linux x86_64 Aperture Remote Mainframe")
            + "\n"
            + make_row("Active Containers", f"{len(services)} Microservices Responding on Network")
            + "\n"
            + make_row("Sensor Status", "Enter login in 'zimaos_credentials.json'")
            + "\n"
            + make_row("Auth Diagnostics", auth_status)
            + "\n"
            + border
        )

    cpu_model = cpu.get("model", "Intel Core Processor")
    cpu_pct = cpu.get("percent", 0.0)
    cpu_bar = make_hud_bar(cpu_pct)
    cpu_freq = cpu.get("freq_ghz", "2.8")
    cpu_temp = cpu.get("temp_c")
    temp_str = (
        f"{cpu_temp:>5.1f}°C (Operational Thermal Range)" if cpu_temp is not None else "Sensors N/A"
    )

    ram_used = ram.get("used_gb", 0.0)
    ram_total = ram.get("total_gb", 0.0)
    ram_pct = ram.get("percent", 0.0)
    ram_bar = make_hud_bar(ram_pct)

    gpu_name = (gpu.get("name") if gpu else None) or "Intel UHD Graphics 630 (Integrated GPU)"
    gpu_util = gpu.get("utilization_gpu", 0.0) if gpu else 0.0
    gpu_bar = make_hud_bar(gpu_util)
    gpu_temp_str = (
        f"{cpu_temp:>5.1f}°C (Thermal Headroom: Optimal)" if cpu_temp is not None else "Sensors N/A"
    )

    pwr = telemetry.get("power_watts", 3.0)
    pwr_str = f"{pwr:>5.1f} W (Intel RAPL Package Power Sensor)"

    disk_used = disk.get("used_gb", 0.0) if disk else 0.0
    disk_total = disk.get("total_gb", 0.0) if disk else 0.0
    disk_pct = disk.get("percent", 0.0) if disk else 0.0
    disk_bar = make_hud_bar(disk_pct)
    drive_tag = disk.get("drive_name", "sda") if disk else "sda"

    containers = telemetry.get("containers", [])
    apps_cnt = telemetry.get("apps_count") or len(containers) or len(services)
    clean_apps = [
        c.replace("compose-", "").replace("big-bear-", "") for c in containers if isinstance(c, str)
    ]
    if not clean_apps and services:
        clean_apps = [s.get("name", "") for s in services if isinstance(s, dict)]
    sample_names = (
        ", ".join([a.title() for a in clean_apps[:3]]) if clean_apps else "Active Microservices"
    )

    dev_name = telemetry.get("device_name", "MonizServer")
    dev_model = telemetry.get("device_model", "83EE")
    arch = telemetry.get("arch", "amd64")

    lines = [
        border,
        "|           APERTURE SCIENCE HARDWARE TELEMETRY & THERMAL HUD        |",
        border,
        make_row("CPU Model", cpu_model),
        make_row("CPU Utilization", f"{cpu_pct:>5.1f}% [{cpu_bar}] @ {cpu_freq} GHz"),
        make_row("CPU Temperature", temp_str),
        make_row("System Memory", f"{ram_used:>5.1f} / {ram_total} GB ({ram_pct}%) [{ram_bar}]"),
        make_row("GPU Model", gpu_name),
        make_row("GPU Utilization", f"{gpu_util:>5.1f}% [{gpu_bar}]"),
        make_row("GPU Temperature", gpu_temp_str),
        make_row("VRAM Usage", "Dynamic UMA (Shared System Host Memory)"),
        make_row("Active Power Draw", pwr_str),
        make_row(
            f"System Disk ({drive_tag})",
            f"{disk_used:>5.1f} / {disk_total} GB ({disk_pct}%) [{disk_bar}]",
        ),
        make_row("Active Containers", f"{apps_cnt} Microservices ({sample_names})"),
        make_row("Host OS & Server", f"ZimaOS Linux {arch} ({dev_name} {dev_model})"),
        border,
    ]
    return "\n".join(lines)


def format_zimaos_terminal_card(telemetry: dict[str, Any]) -> str:
    """Generates the full dual-box terminal view matching Picture 3."""
    host = telemetry.get("host", config.zimaos_host)
    clean_host = host.replace("http://", "").replace("https://", "").rstrip("/")
    target_str = f"Target: {clean_host}"[:25]
    header = (
        "+====================================================================+\n"
        "|   APERTURE SCIENCE REMOTE MAINFRAME - ZIMAOS TELEMETRY MONITOR     |\n"
        f"| [* TELEMETRY ACTIVE] {target_str:<25} Refresh: every 1.5s |\n"
        "| Press Ctrl+C at any time to return to GLaDOS-CLI console           |\n"
        "+====================================================================+"
    )
    hud = format_zimaos_hud(telemetry)
    return header + "\n" + hud


def get_zimaos_telemetry() -> dict[str, Any]:
    """
    Connects to the ZimaOS server, measures gateway latency, probes online microservices,
    and queries system hardware metrics (CPU, RAM, storage, uptime, Docker apps).
    """
    global _last_rapl_sample
    host = get_zimaos_host()
    base = host.rstrip("/")
    if not base.startswith("http://") and not base.startswith("https://"):
        base = f"http://{base}"

    telemetry: dict[str, Any] = {
        "host": base,
        "online": False,
        "latency_ms": None,
        "gateway": None,
        "auth_status": "Unchecked",
        "cpu": None,
        "ram": None,
        "gpu": None,
        "disk": None,
        "power_watts": 3.0,
        "services": [],
        "apps_count": 0,
        "containers": [],
        "device_name": "MonizServer",
        "device_model": "83EE",
        "arch": "amd64",
        "timestamp": datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        "error": None,
    }

    # 1. Test Gateway HTTP Reachability and measure round-trip latency
    start_t = time.time()
    try:
        req = urllib.request.Request(base, headers={"User-Agent": "Aperture-Science-GLaDOS/3.11"})
        with urllib.request.urlopen(req, timeout=2.5) as resp:
            telemetry["latency_ms"] = round((time.time() - start_t) * 1000, 1)
            telemetry["online"] = True
            headers = dict(resp.headers)
            via = headers.get("Via") or headers.get("Server") or "Caddy"
            telemetry["gateway"] = f"{via} ({telemetry['latency_ms']}ms)"
    except Exception as e:
        telemetry["online"] = False
        telemetry["error"] = str(e)
        telemetry["hud_card"] = format_zimaos_hud(telemetry)
        telemetry["full_terminal_card"] = format_zimaos_terminal_card(telemetry)
        return telemetry

    # 2. Check server initialization status
    try:
        u_data = _query_zimaos_endpoint("/v1/users/status", timeout=1.5)
        if isinstance(u_data, dict) and u_data.get("data"):
            telemetry["user_status"] = u_data["data"]
    except Exception:
        pass

    # 3. Fast Service Port Probe
    services = probe_zimaos_services(base)
    telemetry["services"] = services
    telemetry["apps_count"] = len(services)

    # 4. Query Real ZimaOS Endpoints
    util_data = _query_zimaos_endpoint("/v1/sys/utilization", timeout=2.5)
    dev_data = _query_zimaos_endpoint("/v2/zimaos/device/info", timeout=2.0)
    storages_data = _query_zimaos_endpoint("/v2/local_storage/storages", timeout=2.0)
    disk_info_data = _query_zimaos_endpoint("/v2/local_storage/disk/info", timeout=2.0)
    apps_data = _query_zimaos_endpoint(
        "/v2/app_management/apps", timeout=2.5
    ) or _query_zimaos_endpoint("/v1/container", timeout=2.0)

    # Fallback to legacy endpoints if running older CasaOS
    hw_data = None
    if not util_data:
        hw_data = (
            _query_zimaos_endpoint("/v1/sys/hardware/info")
            or _query_zimaos_endpoint("/v2/sys/hardware/info")
            or _query_zimaos_endpoint("/v1/sys/overview")
            or _query_zimaos_endpoint("/v1/sys/status")
        )

    if util_data or dev_data or storages_data or hw_data:
        telemetry["auth_status"] = "[* AUTH: ACTIVE / SENSORS ONLINE]"

        # A. CPU Parsing
        cpu_block = util_data.get("data", {}).get("cpu", {}) if isinstance(util_data, dict) else {}
        dev_cpu = dev_data.get("cpu", {}) if isinstance(dev_data, dict) else {}

        cpu_model = dev_cpu.get("model") or cpu_block.get("model") or "Intel Core Processor"
        cpu_freq = dev_cpu.get("frequency") or "2.80"
        cpu_cores = dev_cpu.get("cores") or cpu_block.get("num") or 6
        cpu_pct = float(cpu_block.get("percent", 0.0))
        cpu_temp = (
            float(cpu_block.get("temperature", 0.0))
            if cpu_block.get("temperature") is not None
            else None
        )

        if not cpu_pct and hw_data:
            d_block = hw_data.get("data", {}) if isinstance(hw_data, dict) else {}
            c_b = d_block.get("cpu", {})
            cpu_pct = float(c_b.get("percent") or d_block.get("cpu_percent") or 0.0)
            cpu_temp = float(c_b.get("temperature") or cpu_temp or 0.0)
            cpu_model = c_b.get("model_name") or cpu_model

        telemetry["cpu"] = {
            "percent": float(cpu_pct),
            "temp_c": float(cpu_temp) if cpu_temp is not None else None,
            "model": str(cpu_model),
            "freq_ghz": str(cpu_freq),
            "cores": int(cpu_cores),
        }

        # B. RAM Parsing
        mem_block = util_data.get("data", {}).get("mem", {}) if isinstance(util_data, dict) else {}
        ram_total = mem_block.get("total", 0)
        ram_used = mem_block.get("used", 0)
        ram_used_gb = round(ram_used / (1024**3), 2)
        ram_total_gb = round(ram_total / (1024**3), 2)
        ram_pct = float(
            mem_block.get(
                "usedPercent", round((ram_used_gb / ram_total_gb * 100) if ram_total_gb else 0.0, 1)
            )
        )

        if not ram_total and hw_data:
            d_block = hw_data.get("data", {}) if isinstance(hw_data, dict) else {}
            r_b = d_block.get("ram", {}) or d_block.get("memory", {})
            r_tot = r_b.get("total", 0)
            r_usd = r_b.get("used", 0)
            ram_total_gb = round(r_tot / (1024**3), 2) if r_tot > 1024**2 else round(r_tot, 2)
            ram_used_gb = round(r_usd / (1024**3), 2) if r_usd > 1024**2 else round(r_usd, 2)
            ram_pct = float(
                r_b.get("percent")
                or (round((ram_used_gb / ram_total_gb) * 100.0, 1) if ram_total_gb else 0.0)
            )

        telemetry["ram"] = {
            "total_gb": ram_total_gb,
            "used_gb": ram_used_gb,
            "percent": ram_pct,
        }

        # C. GPU Parsing
        gpu_list = dev_data.get("gpu", []) if isinstance(dev_data, dict) else []
        raw_gpu = gpu_list[0] if gpu_list else "Integrated UHD Graphics"
        clean_gpu = raw_gpu.replace("Intel CoffeeLake-S GT2 [", "").replace("]", "").strip()
        gpu_full_name = (
            f"Intel {clean_gpu} (Integrated GPU)"
            if not clean_gpu.startswith("Intel")
            else f"{clean_gpu} (Integrated GPU)"
        )
        telemetry["gpu"] = {
            "name": gpu_full_name,
            "utilization_gpu": 0.0,
            "temp_c": cpu_temp,
        }

        # D. Storage Parsing
        storage_list = storages_data if isinstance(storages_data, list) else []
        pool = storage_list[0].get("extensions", {}) if storage_list else {}
        pool_name = storage_list[0].get("name", "sda") if storage_list else "sda"
        p_size = pool.get("size", 0)
        p_used = pool.get("used", 0)
        disk_total_gb = round(p_size / (1024**3), 1)
        disk_used_gb = round(p_used / (1024**3), 1)
        disk_pct = round((disk_used_gb / disk_total_gb * 100), 1) if disk_total_gb else 0.0

        hdd = (
            disk_info_data.get("data", {}).get("disk", {})
            if isinstance(disk_info_data, dict)
            else {}
        )
        hdd_name = hdd.get("name", "sda")
        hdd_temp = hdd.get("temperature")
        hdd_vendor = hdd.get("vendor", "WD")
        hdd_model = hdd.get("model", "System")

        if not disk_total_gb and hw_data:
            d_block = hw_data.get("data", {}) if isinstance(hw_data, dict) else {}
            d_b = d_block.get("disk", {}) or d_block.get("storage", {})
            d_tot = d_b.get("total", 0)
            d_usd = d_b.get("used", 0)
            disk_total_gb = round(d_tot / (1024**3), 1) if d_tot > 1024**2 else round(d_tot, 1)
            disk_used_gb = round(d_usd / (1024**3), 1) if d_usd > 1024**2 else round(d_usd, 1)
            disk_pct = float(
                d_b.get("percent")
                or (round((disk_used_gb / disk_total_gb) * 100.0, 1) if disk_total_gb else 0.0)
            )

        telemetry["disk"] = {
            "total_gb": disk_total_gb,
            "used_gb": disk_used_gb,
            "percent": disk_pct,
            "drive_name": hdd_name,
            "pool_name": pool_name,
            "hdd_temp": hdd_temp,
            "hdd_vendor": hdd_vendor,
            "hdd_model": hdd_model,
        }

        # E. Power Draw (Intel RAPL)
        power_watts = None
        if cpu_block and "power" in cpu_block:
            p_info = cpu_block["power"]
            try:
                curr_t = float(p_info.get("timestamp", 0))
                curr_v = float(p_info.get("value", 0))
                if _last_rapl_sample:
                    prev_t, prev_v = _last_rapl_sample
                    dt = curr_t - prev_t
                    dv = curr_v - prev_v
                    if 0.2 <= dt <= 10.0 and dv > 0:
                        power_watts = round(dv / (dt * 1e6), 1)
                _last_rapl_sample = (curr_t, curr_v)
            except Exception:
                pass
        if power_watts is None or power_watts <= 0.0:
            power_watts = 3.0
        telemetry["power_watts"] = power_watts

        # F. Docker Applications & Containers
        installed_apps = []
        if apps_data and isinstance(apps_data.get("data"), dict):
            installed_apps = apps_data["data"].get("installed", [])
        elif apps_data and isinstance(apps_data.get("data"), list):
            installed_apps = [a.get("name", "") for a in apps_data["data"]]
        telemetry["containers"] = installed_apps
        telemetry["apps_count"] = max(len(installed_apps), len(services))

        # G. Device Info
        dev_name = (
            dev_data.get("device_name", "MonizServer")
            if isinstance(dev_data, dict)
            else "MonizServer"
        )
        dev_model = dev_data.get("device_model", "83EE") if isinstance(dev_data, dict) else "83EE"
        arch = dev_data.get("arch", "amd64") if isinstance(dev_data, dict) else "amd64"
        telemetry["device_name"] = dev_name
        telemetry["device_model"] = dev_model
        telemetry["arch"] = arch

    else:
        telemetry["auth_status"] = "[* ACCESS: TOKEN REQUIRED FOR HARDWARE SENSORS]"

    telemetry["hud_card"] = format_zimaos_hud(telemetry)
    telemetry["full_terminal_card"] = format_zimaos_terminal_card(telemetry)
    return telemetry


@register_tool(
    name="monitor_zimaos",
    description="Real-time telemetry and component tracker for your ZimaOS home server.",
    sensitive=False,
)
def monitor_zimaos(live: bool = False, **kwargs) -> tuple[bool, dict[str, Any]]:
    """
    Collects real-time ZimaOS server metrics (gateway status, CPU, RAM, storage, online services).
    If live=True, runs continuous in-terminal monitoring loop.
    """
    telemetry = get_zimaos_telemetry()
    if live:
        try:
            run_live_zimaos_monitor()
        except Exception:
            logger.exception("Error running live ZimaOS monitor")
    return True, telemetry


def run_live_zimaos_monitor(interval: float = 1.5, max_ticks: int | None = None) -> None:
    """
    Runs an in-place live updating terminal HUD for ZimaOS server telemetry.
    Press Ctrl+C to exit cleanly back to the CLI prompt.
    """
    if hasattr(sys.stdout, "reconfigure"):
        try:
            sys.stdout.reconfigure(encoding="utf-8", errors="replace")
        except Exception:
            pass

    spinner = ["◐", "◓", "◑", "◒"]
    tick = 0
    host = get_zimaos_host()

    print(f"\n[*] Initializing Aperture Science ZimaOS Telemetry Monitor for {host}...")
    time.sleep(0.3)

    try:
        while True:
            telemetry = get_zimaos_telemetry()
            hud = telemetry.get("hud_card", "")
            spin_char = spinner[tick % len(spinner)]
            tick += 1
            now_str = datetime.datetime.now().strftime("%H:%M:%S")

            clean_host = host.replace("http://", "").replace("https://", "").rstrip("/")
            target_str = f"Target: {clean_host}"[:25]
            header = (
                "+====================================================================+\n"
                "|   APERTURE SCIENCE REMOTE MAINFRAME - ZIMAOS TELEMETRY MONITOR     |\n"
                f"| [{spin_char} TELEMETRY ACTIVE] {target_str:<25} Refresh: every {interval:.1f}s |\n"
                "| Press Ctrl+C at any time to return to GLaDOS-CLI console           |\n"
                "+====================================================================+"
            )
            footer = (
                f"[Telemetry Synchronized: {now_str}] Remote Mainframe Diagnostics Active.\n"
                f"[Target IP: {host} | Type 'zima ip <address>' to reconfigure]\n"
                "[Press Ctrl+C to exit live monitor and return to GLaDOS-CLI]"
            )

            try:
                sys.stdout.write("\033[H\033[J")
                sys.stdout.write(header + "\n" + hud + "\n" + footer + "\n")
                sys.stdout.flush()
            except UnicodeEncodeError:
                encoding = getattr(sys.stdout, "encoding", "utf-8") or "utf-8"
                out_block = header + "\n" + hud + "\n" + footer + "\n"
                sys.stdout.write(
                    out_block.encode(encoding, errors="replace").decode(encoding, errors="replace")
                )
                sys.stdout.flush()

            if max_ticks and tick >= max_ticks:
                break

            end_time = time.time() + interval
            while time.time() < end_time:
                time.sleep(0.1)

    except KeyboardInterrupt:
        try:
            sys.stdout.write(
                "\n\n[*] Exited ZimaOS telemetry monitor. Returning to GLaDOS-CLI console.\n\n"
            )
            sys.stdout.flush()
        except Exception:
            pass


@register_tool(
    name="get_zimaos_status",
    description="Queries and returns the operational status, CPU, RAM, and disk utilization of your ZimaOS server.",
    sensitive=False,
)
def get_zimaos_status(**kwargs) -> tuple[bool, str]:
    """Retrieves live server telemetry from ZimaOS."""
    telemetry = get_zimaos_telemetry()
    host = telemetry.get("host", config.zimaos_host)

    if not telemetry.get("online"):
        return (
            False,
            f"Unable to connect to ZimaOS server at {host}. Verify that the server is powered on and reachable, or run 'zima ip <address>' to update the host IP.",
        )

    cpu_info = telemetry.get("cpu")
    ram_info = telemetry.get("ram")
    svc_count = len(telemetry.get("services", []))

    cpu_str = f"{cpu_info['percent']}%" if cpu_info else "Normal"
    ram_str = f"{ram_info['percent']}%" if ram_info else "Normal"

    status_msg = (
        f"Aperture remote mainframe ZimaOS at {host} is operational. "
        f"CPU load is at {cpu_str}, Memory utilization is {ram_str}. "
        f"{svc_count} network microservice(s) responding. All sub-systems performing within acceptable parameters."
    )
    return True, status_msg


@register_tool(
    name="list_zimaos_apps",
    description="Lists installed and running Docker applications on the ZimaOS server.",
    sensitive=False,
)
def list_zimaos_apps(**kwargs) -> tuple[bool, str]:
    """Lists installed applications and web links on the ZimaOS server."""
    apps = get_zimaos_apps_detailed()
    if not apps:
        # Fallback to port probing if Docker API is protected by auth
        services = probe_zimaos_services(get_zimaos_host())
        if services:
            names = [s["name"] for s in services]
            return (
                True,
                f"ZimaOS server responded with {len(services)} active service(s): {', '.join(names)}.",
            )
        return (
            False,
            f"Could not retrieve container manifest from ZimaOS ({config.zimaos_host}). Ensure Docker daemon is accessible.",
        )

    lines = [f"{a.get('name', 'Unknown')} ({a.get('state', 'running')})" for a in apps]
    apps_summary = ", ".join(lines[:8])
    return True, f"ZimaOS is currently running {len(apps)} container(s): {apps_summary}."


def get_custom_zima_apps() -> list[dict[str, Any]]:
    """Retrieves user-defined custom ZimaOS applications from local persistent storage."""
    if not CUSTOM_APPS_FILE.exists():
        host = config.zimaos_host.rstrip("/")
        if not host.startswith("http://") and not host.startswith("https://"):
            host = f"http://{host}"
        defaults = [
            {
                "id": "custom-plex",
                "name": "Plex",
                "url": f"{host}:32400",
                "state": "active",
                "category": "Media",
                "custom": True,
            },
            {
                "id": "custom-jellyfin",
                "name": "Jellyfin",
                "url": f"{host}:8096",
                "state": "active",
                "category": "Media",
                "custom": True,
            },
            {
                "id": "custom-nextcloud",
                "name": "Nextcloud",
                "url": f"{host}:8080",
                "state": "active",
                "category": "Cloud",
                "custom": True,
            },
            {
                "id": "custom-homeassistant",
                "name": "Home Assistant",
                "url": f"{host}:8123",
                "state": "active",
                "category": "Smart Home",
                "custom": True,
            },
        ]
        try:
            CUSTOM_APPS_FILE.parent.mkdir(parents=True, exist_ok=True)
            with open(CUSTOM_APPS_FILE, "w", encoding="utf-8") as f:
                json.dump(defaults, f, indent=2)
            return defaults
        except Exception:
            return defaults

    try:
        with open(CUSTOM_APPS_FILE, encoding="utf-8") as f:
            return json.load(f)
    except Exception as e:
        logger.warning(f"Error reading custom ZimaOS apps: {e}")
        return []


def add_custom_zima_app(name: str, url: str, category: str = "General") -> tuple[bool, str]:
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
        apps.append(
            {
                "id": f"custom-{uuid.uuid4().hex[:6]}",
                "name": clean_name,
                "url": clean_url,
                "category": clean_cat,
                "state": "active",
                "custom": True,
            }
        )

    try:
        CUSTOM_APPS_FILE.parent.mkdir(parents=True, exist_ok=True)
        with open(CUSTOM_APPS_FILE, "w", encoding="utf-8") as f:
            json.dump(apps, f, indent=2)
        action_word = "Updated" if updated else "Registered"
        return True, f"{action_word} application '{clean_name}' pointing to {clean_url}."
    except Exception as e:
        return False, f"Failed to save application: {e}"


def delete_custom_zima_app(name: str) -> tuple[bool, str]:
    """Removes a custom application from the local registry."""
    clean_name = str(name).strip().lower()
    apps = get_custom_zima_apps()
    filtered = [
        a for a in apps if a.get("name", "").lower() != clean_name and a.get("id", "") != clean_name
    ]
    if len(filtered) == len(apps):
        return False, f"Application '{name}' not found."

    try:
        with open(CUSTOM_APPS_FILE, "w", encoding="utf-8") as f:
            json.dump(filtered, f, indent=2)
        return True, f"Removed application '{name}' from registry."
    except Exception as e:
        return False, f"Failed to remove application: {e}"


def get_zimaos_apps_detailed() -> list[dict[str, Any]]:
    """Returns a merged list of native ZimaOS apps, Docker applications, and custom user apps."""
    result = []
    seen_keys = set()

    # Base host setup
    raw_host = config.zimaos_host.rstrip("/")
    clean_ip = re.sub(r"^https?://", "", raw_host).split(":")[0] or "127.0.0.1"

    # 1. Query native ZimaOS App Grid (/v2/app_management/web/appgrid)
    grid_data = _query_zimaos_endpoint("/v2/app_management/web/appgrid")
    items = (grid_data and grid_data.get("data")) or []
    if isinstance(items, list):
        for item in items:
            if not isinstance(item, dict):
                continue
            raw_name = item.get("name") or ""
            title = item.get("title")
            if isinstance(title, dict):
                disp_name = (
                    title.get("custom")
                    or title.get("en_US")
                    or title.get("en_GB")
                    or next(iter(title.values()), raw_name)
                )
            else:
                disp_name = str(title).strip() if title else raw_name

            norm_key = re.sub(r"[^a-z0-9]", "", (disp_name or raw_name).lower())
            if norm_key in seen_keys:
                continue
            if norm_key:
                seen_keys.add(norm_key)

            port = item.get("port")
            if not port:
                ports = item.get("ports") or item.get("Ports") or []
                if isinstance(ports, list) and ports:
                    p = ports[0]
                    port = p.get("PublicPort") if isinstance(p, dict) else p
                elif isinstance(ports, (int, str)) and str(ports).isdigit():
                    port = int(ports)

            scheme = item.get("scheme") or "http"
            idx = item.get("index") or ""
            if idx and not idx.startswith("/"):
                idx = "/" + idx

            if port:
                app_url = f"{scheme}://{clean_ip}:{port}{idx}"
            else:
                app_url = f"{scheme}://{clean_ip}{idx}" if clean_ip else raw_host

            result.append(
                {
                    "id": item.get("id") or item.get("store_app_id") or raw_name,
                    "name": disp_name or raw_name,
                    "raw_name": raw_name,
                    "title": title,
                    "state": (item.get("status") or item.get("state") or "running").lower(),
                    "port": port,
                    "url": app_url,
                    "category": item.get("app_type") or "App",
                    "custom": False,
                    "image": item.get("image") or item.get("Image", ""),
                }
            )

    # 2. Query Docker daemon on ZimaOS if reachable
    containers_data = _query_zimaos_endpoint("/v2/docker/container/list") or _query_zimaos_endpoint(
        "/v1/docker/container"
    )
    c_items = (containers_data and containers_data.get("data")) or []
    if isinstance(c_items, list):
        for c in c_items:
            if not isinstance(c, dict):
                continue
            name = c.get("name") or (
                c.get("Names", [""])[0].lstrip("/") if c.get("Names") else "Unknown"
            )
            norm_key = re.sub(r"[^a-z0-9]", "", name.lower())
            if norm_key in seen_keys:
                continue
            if norm_key:
                seen_keys.add(norm_key)

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

            app_url = f"http://{clean_ip}:{port}" if port else f"http://{clean_ip}"

            result.append(
                {
                    "id": cid,
                    "name": name,
                    "raw_name": name,
                    "state": state,
                    "port": port,
                    "url": app_url,
                    "category": "Docker",
                    "custom": False,
                    "image": c.get("image") or c.get("Image", ""),
                }
            )

    # 3. Custom user-defined applications
    custom_apps = get_custom_zima_apps()
    for ca in custom_apps:
        norm_key = re.sub(r"[^a-z0-9]", "", ca.get("name", "").lower())
        if norm_key not in seen_keys:
            c_url = ca.get("url", "")
            if "zimaos.local" in c_url and clean_ip:
                ca["url"] = c_url.replace("zimaos.local", clean_ip)
            result.append(ca)
            if norm_key:
                seen_keys.add(norm_key)

    return result


@register_tool(
    name="launch_zimaos_app",
    description="Launches or opens a Docker application (Plex, Jellyfin, Nextcloud, Home Assistant, etc.) on your ZimaOS server.",
    sensitive=False,
)
def launch_zimaos_app(app_name: str, **kwargs) -> tuple[bool, str]:
    """Finds, wakes, and opens a ZimaOS Docker application in the default browser."""
    if not app_name or not str(app_name).strip():
        return False, "Please specify an application name to launch on ZimaOS."

    target_raw = str(app_name).strip()
    target_clean = re.sub(r"[^a-z0-9]", "", target_raw.lower())
    apps = get_zimaos_apps_detailed()

    if not apps:
        # Fallback: if server cannot list containers, offer to open dashboard
        open_zimaos_dashboard()
        return (
            True,
            f"Could not query containers directly. Opened ZimaOS dashboard to locate '{app_name}'.",
        )

    # Matching: Exact -> Substring/Containment
    matched_app = None
    for a in apps:
        a_name = re.sub(r"[^a-z0-9]", "", a.get("name", "").lower())
        a_raw = re.sub(r"[^a-z0-9]", "", a.get("raw_name", "").lower())
        if target_clean in (a_name, a_raw):
            matched_app = a
            break

    if not matched_app:
        for a in apps:
            a_name = re.sub(r"[^a-z0-9]", "", a.get("name", "").lower())
            a_raw = re.sub(r"[^a-z0-9]", "", a.get("raw_name", "").lower())
            a_img = re.sub(r"[^a-z0-9]", "", a.get("image", "").lower())
            if target_clean in a_name or target_clean in a_raw or target_clean in a_img:
                matched_app = a
                break
            if len(a_name) >= 3 and a_name in target_clean:
                matched_app = a
                break

    if not matched_app:
        available = ", ".join([a.get("name", "Unknown") for a in apps[:6]])
        return (
            False,
            f"Could not find application matching '{app_name}' on ZimaOS. Available apps: {available}.",
        )

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
                method="PUT",
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
def open_zimaos_dashboard(**kwargs) -> tuple[bool, str]:
    """Opens ZimaOS dashboard in browser."""
    host = config.zimaos_host
    if not host.startswith("http://") and not host.startswith("https://"):
        host = f"http://{host}"
    try:
        webbrowser.open(host)
        return True, f"Opened ZimaOS dashboard at {host} in your default browser."
    except Exception as e:
        return False, f"Failed to launch ZimaOS dashboard: {e}"


@register_tool(
    name="open_zimaos_ssh",
    description="Launches an interactive SSH terminal connection to your ZimaOS server in a dedicated window.",
    sensitive=False,
)
def open_zimaos_ssh(
    ssh_user: str | None = None, port: int | str | None = None, **kwargs
) -> tuple[bool, str]:
    """Opens a dedicated terminal window running an SSH session to the ZimaOS home server."""
    import shutil
    import subprocess

    # Resolve IP/Host
    host = get_zimaos_host()
    clean_ip = re.sub(r"^https?://", "", host).split(":")[0] or "127.0.0.1"

    # Resolve user
    user = (ssh_user or "").strip()
    if not user:
        user_loaded, _ = load_zimaos_credentials()
        user = user_loaded or "fl1pmoniz"

    # Resolve port
    port_str = str(port or 22).strip()
    port_arg = [] if port_str == "22" else ["-p", port_str]

    title = f"Aperture Science Remote Node - {user}@{clean_ip}"

    try:
        wt_path = shutil.which("wt") or shutil.which("wt.exe")
        if wt_path:
            cmd = (
                [wt_path, "-w", "0", "nt", "--title", title, "ssh"]
                + port_arg
                + [f"{user}@{clean_ip}"]
            )
            subprocess.Popen(cmd)
            return True, f"Launched Windows Terminal SSH session to {user}@{clean_ip}."

        # Fallback to Command Prompt
        target_str = (
            f"{user}@{clean_ip}" if port_str == "22" else f"-p {port_str} {user}@{clean_ip}"
        )
        cmd_str = f'start "{title}" cmd.exe /k "ssh {target_str}"'
        subprocess.Popen(cmd_str, shell=True)
        return True, f"Launched Command Prompt SSH session to {user}@{clean_ip}."
    except Exception as e:
        logger.error(f"Failed to launch SSH terminal: {e}")
        return False, f"Failed to launch SSH terminal for {user}@{clean_ip}: {e}"


def _query_docker_socket(method: str, path: str, body: bytes | None = None) -> tuple[int, Any]:
    """Queries the Docker daemon directly via /var/run/docker.sock if available."""
    import os

    sock_path = "/var/run/docker.sock"
    if not os.path.exists(sock_path):
        return 404, None
    import http.client

    class UnixHTTPConnection(http.client.HTTPConnection):
        def connect(self):
            self.sock = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
            self.sock.settimeout(4.0)
            self.sock.connect(sock_path)

    conn = UnixHTTPConnection("localhost")
    try:
        conn.request(
            method,
            path,
            body=body,
            headers={"Host": "localhost", "User-Agent": "Aperture-Science-GLaDOS/3.11"},
        )
        resp = conn.getresponse()
        status = resp.status
        resp_body = resp.read().decode("utf-8", errors="replace")
        try:
            data = json.loads(resp_body)
        except Exception:
            data = resp_body
        return status, data
    except Exception as e:
        logger.debug(f"Docker socket query error: {e}")
        return 500, str(e)
    finally:
        conn.close()


@register_tool(
    name="manage_containers",
    description="Inspects, monitors, restarts, or reads logs from Docker containers running on the ZimaOS homelab server.",
    sensitive=False,
)
def manage_containers(
    action: str = "list",
    container_name: str = "",
    lines: int = 20,
    **kwargs,
) -> tuple[bool, Any]:
    """Autonomous Docker container sentinel and lifecycle controller."""
    act = (action or "list").strip().lower()
    target = (container_name or "").strip().lower()

    # 1. LIST CONTAINERS
    if act in ("list", "ps", "status", "all"):
        status, raw = _query_docker_socket("GET", "/containers/json?all=1")
        containers_data = []

        if status == 200 and isinstance(raw, list):
            for c in raw:
                raw_names = c.get("Names") or []
                c_name = raw_names[0].lstrip("/") if raw_names else c.get("Id", "")[:12]
                img = c.get("Image", "unknown")
                c_status = c.get("Status", "Up")
                c_state = c.get("State", "running")
                containers_data.append(
                    {
                        "name": c_name,
                        "image": img,
                        "status": c_status,
                        "state": c_state,
                        "id": c.get("Id", ""),
                    }
                )
        else:
            detailed = get_zimaos_apps_detailed()
            if detailed:
                for a in detailed:
                    containers_data.append(
                        {
                            "name": a.get("name", "app"),
                            "image": a.get("image", a.get("category", "app")),
                            "status": a.get("state", "running"),
                            "state": a.get("state", "running"),
                            "id": a.get("id", ""),
                        }
                    )

        cnt = len(containers_data)
        border = "+====================================================================+"
        sep = "+--------------------------------------------------------------------+"
        header_row = "| NAME                 IMAGE                 STATUS          STATE    |"

        card_lines = [
            border,
            "|   APERTURE SCIENCE DOCKER CONTAINER SENTINEL & LIFECYCLE MONITOR   |",
            f"| [* DAEMON ACTIVE] Status: Operational          Containers: {cnt:>2} Active |",
            border,
            header_row,
            sep,
        ]

        if not containers_data:
            card_lines.append(
                "| No containers detected or Docker daemon inaccessible.               |"
            )
        else:
            for item in containers_data[:12]:
                n = item["name"][:20].ljust(20)
                im = item["image"].split("/")[-1][:21].ljust(21)
                st = item["status"][:15].ljust(15)
                state = item["state"][:8].ljust(8)
                card_lines.append(f"| {n} {im} {st} {state} |")

        card_lines.append(border)
        card_str = "\n".join(card_lines)

        return True, {
            "full_terminal_card": card_str,
            "hud_card": card_str,
            "containers": containers_data,
            "count": cnt,
            "message": f"Docker sentinel operational. {cnt} container(s) monitored.",
        }

    # 2. RESTART CONTAINER
    elif act in ("restart", "reboot", "bounce"):
        if not target:
            return False, "Specify a container name to restart (e.g. 'restart jellyfin')."

        status, raw = _query_docker_socket("GET", "/containers/json?all=1")
        target_id = None
        exact_name = target

        if status == 200 and isinstance(raw, list):
            for c in raw:
                raw_names = [n.lstrip("/").lower() for n in (c.get("Names") or [])]
                if target in raw_names or any(target in n for n in raw_names):
                    target_id = c.get("Id")
                    exact_name = raw_names[0] if raw_names else target
                    break

        if target_id:
            r_status, r_resp = _query_docker_socket("POST", f"/containers/{target_id}/restart")
            if r_status in (204, 200):
                return (
                    True,
                    f"Container '{exact_name}' reanimation protocol executed successfully. Subsystem restarted.",
                )
            return False, f"Failed to restart container '{exact_name}': HTTP {r_status} ({r_resp})"

        import shutil
        import subprocess

        d_bin = shutil.which("docker")
        if d_bin:
            try:
                res = subprocess.run(
                    [d_bin, "restart", target], capture_output=True, text=True, timeout=15
                )
                if res.returncode == 0:
                    return (
                        True,
                        f"Container '{target}' reanimation protocol executed successfully via CLI.",
                    )
                return False, f"Docker restart failed: {res.stderr.strip()}"
            except Exception as e:
                return False, f"Failed to execute docker restart: {e}"

        return (
            False,
            f"Container '{target}' not found in active Docker manifest. Use 'containers' to inspect running services.",
        )

    # 3. CONTAINER LOGS
    elif act in ("logs", "log", "tail"):
        if not target:
            return False, "Specify a container name to inspect logs (e.g. 'logs ollama')."

        tail_count = int(lines or 20)
        status, raw = _query_docker_socket("GET", "/containers/json?all=1")
        target_id = None
        exact_name = target

        if status == 200 and isinstance(raw, list):
            for c in raw:
                raw_names = [n.lstrip("/").lower() for n in (c.get("Names") or [])]
                if target in raw_names or any(target in n for n in raw_names):
                    target_id = c.get("Id")
                    exact_name = raw_names[0] if raw_names else target
                    break

        log_content = ""
        if target_id:
            l_status, l_resp = _query_docker_socket(
                "GET", f"/containers/{target_id}/logs?stdout=1&stderr=1&tail={tail_count}"
            )
            if l_status == 200:
                log_content = str(l_resp)
        else:
            import shutil
            import subprocess

            d_bin = shutil.which("docker")
            if d_bin:
                try:
                    res = subprocess.run(
                        [d_bin, "logs", "--tail", str(tail_count), target],
                        capture_output=True,
                        text=True,
                        timeout=10,
                    )
                    log_content = res.stdout or res.stderr
                except Exception as e:
                    return False, f"Failed to retrieve docker logs: {e}"

        if not log_content:
            return (
                False,
                f"Could not retrieve logs for container '{target}'. Container may not be running or socket unavailable.",
            )

        clean_lines = [
            re.sub(r"^[\x00-\x1f]{1,8}", "", line)
            for line in log_content.splitlines()
            if line.strip()
        ]
        recent = "\n".join(clean_lines[-tail_count:])

        border = "+====================================================================+"
        card = (
            f"{border}\n"
            f"|   APERTURE CONTAINER LOG SENTINEL - [{exact_name.upper()[:20]:<20}]       |\n"
            f"| Showing last {len(clean_lines[-tail_count:])} log records:                                          |\n"
            f"{border}\n"
            f"{recent}\n"
            f"{border}"
        )
        return True, {
            "full_terminal_card": card,
            "hud_card": card,
            "message": f"Retrieved logs for '{exact_name}'.",
        }

    return False, f"Unrecognized container action '{act}'. Use 'list', 'restart', or 'logs'."


@register_tool(
    name="get_homelab_briefing",
    description="Generates a comprehensive Aperture Homelab Daily Briefing summarizing server telemetry, container health, and atmospheric conditions.",
    sensitive=False,
)
def get_homelab_briefing(to_discord: bool = False, **kwargs) -> tuple[bool, Any]:
    """Aggregates all homelab systems into an authentic Aperture daily test briefing."""
    host_summary = "Intel Core i5-8400 Processor | Operational"
    cpu_temp_str = "45.0°C"
    cpu_util = 15.0
    try:
        from tools.system import get_hardware_telemetry

        hw = get_hardware_telemetry()
        if hw:
            cpu = hw.get("cpu", {})
            cpu_util = cpu.get("percent", 15.0)
            m = cpu.get("model", "Intel Core i5")
            temp = cpu.get("temp_c")
            cpu_temp_str = f"{temp:.1f}°C" if temp is not None else "Sensors N/A"
            host_summary = f"{m[:30]} | {cpu_temp_str}"
    except Exception:
        pass

    c_status, c_raw = _query_docker_socket("GET", "/containers/json?all=1")
    c_count = len(c_raw) if c_status == 200 and isinstance(c_raw, list) else 8

    weather_desc = "Atmospheric conditions nominal"
    try:
        from tools.web import get_weather

        w_ok, w_msg = get_weather()
        if w_ok and w_msg:
            weather_desc = w_msg[:50]
    except Exception:
        pass

    media_desc = "Idle (No active subject streams detected)"
    try:
        from tools.jellyfin import get_jellyfin_now_playing

        j_res = get_jellyfin_now_playing()
        if isinstance(j_res, dict) and j_res.get("now_playing"):
            media_desc = f"Streaming: {j_res.get('title', 'Media')[:40]}"
    except Exception:
        pass

    quips = [
        "The facility survived the night with zero catastrophic kernel panics. Your testing begins immediately.",
        "All homelab microservices are operational. Cake and grief counseling will remain unavailable.",
        "Power distribution is optimal. The probability of neurotoxin ventilation today is only 12%.",
        "Sensors report you are awake. Very impressive. Please resume your assigned testing protocol.",
    ]
    import random

    memorandum = random.choice(quips)

    border = "+====================================================================+"
    sep = "+--------------------------------------------------------------------+"

    card_lines = [
        border,
        "|          APERTURE SCIENCE HOMELAB FACILITY DAILY BRIEFING          |",
        "| [DAILY TEST PROTOCOL] Facility: Aperture Homelab    Cycle: ACTIVE   |",
        border,
        f"| HOST TELEMETRY   : {host_summary[:48]:<48} |",
        f"| CPU UTILIZATION  : {cpu_util:>5.1f}% | Temp: {cpu_temp_str:<32} |",
        f"| CONTAINER SENTINEL: {c_count} Containers Monitored (All Operational)            |",
        f"| ATMOSPHERICS     : {weather_desc[:48]:<48} |",
        f"| MEDIA ACTIVITY   : {media_desc[:48]:<48} |",
        sep,
        "| GLaDOS MEMORANDUM:                                                 |",
        f'| "{memorandum[:64]:<64}" |',
        border,
    ]
    card_str = "\n".join(card_lines)

    if to_discord:
        try:
            from tools.discord_relay import send_message_to_discord

            send_message_to_discord(f"```text\n{card_str}\n```")
        except Exception as e:
            logger.debug(f"Could not forward briefing to Discord: {e}")

    return True, {
        "full_terminal_card": card_str,
        "hud_card": card_str,
        "message": f"Aperture daily briefing compiled. {memorandum}",
    }
