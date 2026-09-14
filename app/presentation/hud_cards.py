"""ASCII telemetry and status HUD card formatters for terminal display.

All formatting uses strict monospaced box-drawing ASCII lines with zero emojis.
"""

from __future__ import annotations

from typing import Any


def format_ascii_box(title: str, rows: list[tuple[str, str]], width: int = 70) -> str:
    """Constructs a standardized monospaced ASCII bordered card.

    Args:
        title: Centered header text.
        rows: List of (label, value) key-value pairs.
        width: Total width of the ASCII card in characters.
    """
    inner_width = width - 4
    border = "+" + "-" * (width - 2) + "+"

    centered_title = title.center(inner_width)
    title_line = f"| {centered_title} |"

    output_lines = [border, title_line, border]

    for label, val in rows:
        prefix = f"| {label.ljust(20)}: "
        remaining_space = width - len(prefix) - 2
        truncated_val = str(val)[:remaining_space].ljust(remaining_space)
        output_lines.append(f"{prefix}{truncated_val} |")

    output_lines.append(border)
    return "\n".join(output_lines)


def format_system_hardware_card(metrics: dict[str, Any]) -> str:
    """Formats system CPU, RAM, Disk, and GPU stats into an ASCII HUD card."""
    rows = [
        ("Host Platform", f"{metrics.get('os_name', 'OS')} ({metrics.get('hostname', 'Local')})"),
        ("CPU Usage", f"{metrics.get('cpu_percent', 0.0)}% ({metrics.get('cpu_count', 0)} cores)"),
        (
            "System RAM",
            f"{metrics.get('ram_used_gb', 0.0):.1f} / {metrics.get('ram_total_gb', 0.0):.1f} GB ({metrics.get('ram_percent', 0.0)}%)",
        ),
        (
            "Primary Disk",
            f"{metrics.get('disk_free_gb', 0.0):.1f} GB Free ({metrics.get('disk_percent', 0.0)}% Used)",
        ),
    ]

    if "gpu_name" in metrics:
        rows.append(("Active GPU", str(metrics.get("gpu_name"))))
        if "gpu_load" in metrics:
            rows.append(("GPU Utilization", f"{metrics.get('gpu_load', 0.0)}%"))
        if "vram_used_mb" in metrics:
            rows.append(
                (
                    "VRAM Memory",
                    f"{metrics.get('vram_used_mb', 0)} / {metrics.get('vram_total_mb', 0)} MB",
                )
            )

    return format_ascii_box("APERTURE SCIENCE SYSTEM TELEMETRY HUD", rows)


def format_flight_radar_card(flight: dict[str, Any]) -> str:
    """Formats live ADS-B airspace radar telemetry into an ASCII HUD card."""
    callsign = flight.get("callsign", "N/A")
    route = f"{flight.get('origin', '???')} -> {flight.get('dest', '???')}"
    status = flight.get("status", "Active").upper()
    eta = flight.get("eta_str", "In Flight")
    model = flight.get("model", "Unknown Aircraft")
    reg = flight.get("reg", "Unknown Reg")
    alt = f"{flight.get('altitude_ft', 0):,} FT ({flight.get('altitude_m', 0):,} m)"
    speed = f"{flight.get('speed_kts', 0)} KTS ({flight.get('speed_kmh', 0)} km/h)"
    heading = f"{flight.get('heading', 0)} deg ({flight.get('cardinal', 'N')})"
    coords = f"{flight.get('lat', 0.0):.4f} deg, {flight.get('lon', 0.0):.4f} deg"
    url = flight.get("fr24_url", f"https://www.flightradar24.com/{callsign}")

    rows = [
        ("Callsign / Flight", callsign),
        ("Airspace Route", route),
        ("Radar Status", f"[{status}]"),
        ("Predicted Landing", eta),
        ("Aircraft Model", model),
        ("Registration", reg),
        ("Live Altitude", alt),
        ("Ground Speed", speed),
        ("Flight Heading", heading),
        ("Coordinates", coords),
        ("Live Radar URL", url),
    ]
    return format_ascii_box("APERTURE SCIENCE AIRSPACE RADAR TELEMETRY HUD", rows)


def format_zimaos_server_card(telemetry: dict[str, Any]) -> str:
    """Formats remote ZimaOS homelab server stats into an ASCII HUD card."""
    host = telemetry.get("host", "Unknown Host")
    status = telemetry.get("status", "Reachable").upper()
    cpu = f"{telemetry.get('cpu_usage', 0.0)}%"
    ram = (
        f"{telemetry.get('ram_used_gb', 0.0):.1f} / {telemetry.get('ram_total_gb', 0.0):.1f} GB"
    )
    storage = f"{telemetry.get('disk_free_gb', 0.0):.1f} GB Free"
    containers = f"{telemetry.get('active_containers', 0)} Active"

    rows = [
        ("Server Host", host),
        ("Connection State", f"[{status}]"),
        ("Remote CPU Load", cpu),
        ("Remote RAM", ram),
        ("Storage Free", storage),
        ("Docker Apps", containers),
    ]
    return format_ascii_box("ZIMAOS HOMELAB SERVER TELEMETRY HUD", rows)
