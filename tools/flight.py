"""Flightradar24 live flight tracking integration for GLaDOS.

Queries Flightradar24 search endpoints and sector feeds to retrieve real-time
flight telemetry (altitude, speed, heading, aircraft model, route, status)
without requiring API keys or subscriptions.
"""

import json
import logging
import re
import urllib.parse
import urllib.request
import webbrowser
from typing import Any, Tuple

from tools import register_tool

logger = logging.getLogger("local_os_agent.tools.flight")

BROWSER_HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36",
    "Accept": "application/json, text/plain, */*",
    "Accept-Language": "en-US,en;q=0.9",
}


def clean_flight_query(query: str) -> str:
    """Cleans user spoken query into standard flight/callsign format (e.g. 'AA 100' -> 'AA100')."""
    clean = query.strip().upper()
    for prefix in ("TRACK FLIGHT", "WHERE IS FLIGHT", "WHERE IS", "TRACK", "FLIGHT", "VOO"):
        if clean.startswith(prefix):
            clean = clean[len(prefix):].strip()
    # Remove internal space between airline code and number (e.g. 'DL 450' -> 'DL450')
    clean = re.sub(r"^([A-Z]{2,3})\s+(\d+)$", r"\1\2", clean)
    return clean.strip(" #:")


def fetch_flightradar24_search(query: str) -> list[dict[str, Any]]:
    """Searches Flightradar24 for active flights matching the query."""
    try:
        encoded = urllib.parse.quote_plus(query)
        url = f"https://www.flightradar24.com/v1/search/web/find?query={encoded}&limit=5"
        req = urllib.request.Request(url, headers=BROWSER_HEADERS)
        with urllib.request.urlopen(req, timeout=6) as resp:
            data = json.loads(resp.read().decode("utf-8"))
        return data.get("results", [])
    except Exception as e:
        logger.debug(f"Flightradar24 search error for '{query}': {e}")
        return []


def fetch_live_sector_telemetry(lat: float, lon: float, flight_id: str) -> dict[str, Any] | None:
    """Queries Flightradar24 localized live feed around the aircraft coordinates."""
    try:
        feed_url = (
            f"https://data-cloud.flightradar24.com/zones/fcgi/feed.js?"
            f"bounds={lat+1.5:.2f},{lat-1.5:.2f},{lon-1.5:.2f},{lon+1.5:.2f}&faa=1&satellite=1&mlat=1&flarm=1&adsb=1"
        )
        req = urllib.request.Request(feed_url, headers=BROWSER_HEADERS)
        with urllib.request.urlopen(req, timeout=6) as resp:
            feed_data = json.loads(resp.read().decode("utf-8"))

        plane_entry = feed_data.get(flight_id)
        if not plane_entry or not isinstance(plane_entry, list):
            return None

        # Feed index mapping:
        # 0=lat, 1=lon, 2=track, 3=alt, 4=spd, 8=model, 9=reg, 11=orig, 12=dest, 13=flight, 14=on_ground, 15=vspd, 16=callsign
        return {
            "lat": plane_entry[0],
            "lon": plane_entry[1],
            "heading": plane_entry[2],
            "altitude_ft": plane_entry[3],
            "speed_kts": plane_entry[4],
            "speed_kmh": int(round(plane_entry[4] * 1.852)),
            "model": plane_entry[8] or "Aircraft",
            "reg": plane_entry[9] or "Unknown",
            "origin": plane_entry[11] or "Unknown",
            "dest": plane_entry[12] or "Unknown",
            "flight": plane_entry[13] or "Unknown",
            "on_ground": bool(plane_entry[14]),
            "vertical_speed_fpm": plane_entry[15],
            "callsign": plane_entry[16] or "Unknown",
        }
    except Exception as e:
        logger.debug(f"Telemetry fetch error for flight {flight_id}: {e}")
        return None


@register_tool(
    name="track_flight",
    description="Tracks a live aircraft using Flightradar24 real-time telemetry (altitude, speed, route, aircraft type, and status).",
    sensitive=False,
)
def track_flight(flight_query: str, open_browser: bool = False, **kwargs) -> Tuple[bool, str]:
    """
    Looks up live flight telemetry from Flightradar24.
    If open_browser=True or if requested in prompt, opens the live radar tracker in browser.
    """
    clean = clean_flight_query(flight_query)
    if not clean:
        return False, "Please specify a flight number to track (e.g. DL450, AA100, TAP123)."

    try:
        results = fetch_flightradar24_search(clean)
        live_matches = [r for r in results if r.get("type") == "live"]

        if not live_matches:
            # Fallback: check if search returned scheduled or recent flight info
            if results:
                first = results[0]
                label = first.get("label", clean)
                return False, f"Flight '{clean}' ({label}) was found in archives, but is not currently airborne on live radar."
            return False, f"No active flight matching '{clean}' could be located on Flightradar24."

        match = live_matches[0]
        flight_id = match.get("id", "")
        detail = match.get("detail", {})
        lat = detail.get("lat")
        lon = detail.get("lon")
        label = match.get("label", clean)

        telemetry = None
        if lat is not None and lon is not None:
            telemetry = fetch_live_sector_telemetry(lat, lon, flight_id)

        # Build telemetry summary
        flight_num = (telemetry and telemetry.get("flight")) or detail.get("flight") or clean
        model = (telemetry and telemetry.get("model")) or detail.get("ac_type") or "Aircraft"
        orig = (telemetry and telemetry.get("origin")) or detail.get("schd_from") or "Unknown"
        dest = (telemetry and telemetry.get("dest")) or detail.get("schd_to") or "Unknown"
        alt = (telemetry and telemetry.get("altitude_ft"))
        spd = (telemetry and telemetry.get("speed_kts"))
        spd_kmh = (telemetry and telemetry.get("speed_kmh"))
        hdg = (telemetry and telemetry.get("heading"))
        reg = (telemetry and telemetry.get("reg")) or detail.get("reg") or ""

        # Determine flight profile status
        vspd = (telemetry and telemetry.get("vertical_speed_fpm")) or 0
        if telemetry and telemetry.get("on_ground"):
            status_desc = "On ground / Taxiing"
        elif vspd > 400:
            status_desc = "Climbing"
        elif vspd < -400:
            status_desc = "Descending for approach"
        else:
            status_desc = "Cruising"

        alt_str = f"{alt:,} feet" if alt is not None else "Altitude unavailable"
        spd_str = f"{spd} knots ({spd_kmh} km/h)" if spd is not None else "Speed unavailable"

        speech = (
            f"Flight {flight_num}, an {model} en route from {orig} to {dest}, is currently {status_desc} "
            f"at {alt_str} at {spd_str}."
        )

        # Broadcast structured telemetry to UI
        flight_data = {
            "callsign": clean,
            "flight_number": flight_num,
            "model": model,
            "origin": orig,
            "dest": dest,
            "altitude_ft": alt,
            "speed_kts": spd,
            "speed_kmh": spd_kmh,
            "heading": hdg,
            "reg": reg,
            "status": status_desc,
            "lat": lat,
            "lon": lon,
            "fr24_url": f"https://www.flightradar24.com/{clean}"
        }
        try:
            from ui.state import ui_state
            ui_state.update(tracked_flight=flight_data)
        except Exception:
            pass

        if open_browser:
            webbrowser.open(f"https://www.flightradar24.com/{clean}")

        return True, speech
    except Exception as e:
        logger.exception(f"Failed to track flight '{flight_query}': {e}")
        return False, f"Aperture Science airspace radar telemetry failed: {e}"

