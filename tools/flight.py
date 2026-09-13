"""Flightradar24 live flight tracking integration for GLaDOS.

Queries Flightradar24 search endpoints and sector feeds to retrieve real-time
flight telemetry (altitude, speed, heading, aircraft model, route, status,
predicted minutes until landing, and live auto-updating radar).
"""

import json
import logging
import math
import os
import re
import sys
import threading
import time
import urllib.parse
import urllib.request
import webbrowser
from datetime import datetime, timezone, timedelta
from typing import Any, Tuple

from config import config
from tools import register_tool

logger = logging.getLogger("local_os_agent.tools.flight")

TRACKED_FLIGHT_FILE = config.captures_dir / "tracked_flight.json"

# Top worldwide commercial airport coordinates (IATA -> (lat, lon))
POPULAR_AIRPORTS: dict[str, tuple[float, float]] = {
    # Americas
    "JFK": (40.6413, -73.7781), "EWR": (40.6895, -74.1745), "LGA": (40.7769, -73.8740),
    "LAX": (33.9416, -118.4085), "ORD": (41.9742, -87.9073), "ATL": (33.6407, -84.4277),
    "DFW": (32.8998, -97.0403), "DEN": (39.8561, -104.6737), "SFO": (37.6213, -122.3790),
    "MIA": (25.7959, -80.2870), "BOS": (42.3656, -71.0096), "MCO": (28.4312, -81.3081),
    "SEA": (47.4502, -122.3088), "LAS": (36.0840, -115.1537), "PHX": (33.4373, -112.0078),
    "IAH": (29.9902, -95.3368), "CLT": (35.2140, -80.9431), "DTW": (42.2162, -83.3554),
    "MSP": (44.8848, -93.2223), "PHL": (39.8729, -75.2437), "YYZ": (43.6777, -79.6248),
    "YVR": (49.1967, -123.1815), "YUL": (45.4657, -73.7455), "MEX": (19.4361, -99.0719),
    "CUN": (21.0365, -86.8771), "PTY": (9.0714, -79.3835), "BOG": (4.7016, -74.1469),
    "GRU": (-23.4356, -46.4731), "GIG": (-22.8089, -43.2436), "BSB": (-15.8697, -47.9172),
    "EZE": (-34.8222, -58.5358), "SCL": (-33.3930, -70.7858), "LIM": (-12.0219, -77.1143),
    "SDQ": (18.4297, -69.6689), "PUJ": (18.5674, -68.3634), "SJU": (18.4394, -66.0018),
    # Europe
    "LHR": (51.4700, -0.4543), "LGW": (51.1537, -0.1821), "CDG": (49.0097, 2.5479),
    "ORY": (48.7262, 2.3652), "FRA": (50.0379, 8.5622), "MUC": (48.3537, 11.7750),
    "AMS": (52.3105, 4.7683), "MAD": (40.4839, -3.5680), "BCN": (41.2974, 2.0833),
    "FCO": (41.8003, 12.2389), "MXP": (45.6301, 8.7255), "ZRH": (47.4582, 8.5555),
    "VIE": (48.1103, 16.5697), "BRU": (50.9010, 4.4856), "CPH": (55.6180, 12.6508),
    "OSL": (60.1976, 11.1004), "ARN": (59.6498, 17.9238), "HEL": (60.3172, 24.9633),
    "DUB": (53.4264, -6.2499), "MAN": (53.3588, -2.2727), "EDI": (55.9508, -3.3725),
    "LIS": (38.7742, -9.1342), "OPO": (41.2421, -8.6786), "ATH": (37.9364, 23.9484),
    "IST": (41.2753, 28.7519), "SAW": (40.8986, 29.3092), "WAW": (52.1672, 20.9679),
    # Middle East & Asia & Oceania & Africa
    "DXB": (25.2532, 55.3657), "AUH": (24.4330, 54.6511), "DOH": (25.2731, 51.6081),
    "RUH": (24.9576, 46.6988), "JED": (21.6796, 39.1565), "HND": (35.5494, 139.7798),
    "NRT": (35.7720, 140.3929), "KIX": (34.4320, 135.2304), "ICN": (37.4602, 126.4407),
    "PEK": (40.0799, 116.6031), "PKX": (39.5098, 116.4105), "PVG": (31.1443, 121.8083),
    "HKG": (22.3080, 113.9185), "TPE": (25.0797, 121.2342), "BKK": (13.6900, 100.7501),
    "SIN": (1.3644, 103.9915), "KUL": (2.7456, 101.7099), "CGK": (-6.1256, 106.6559),
    "DEL": (28.5562, 77.1000), "BOM": (19.0896, 72.8656), "BLR": (13.1986, 77.7066),
    "SYD": (-33.9399, 151.1753), "MEL": (-37.6690, 144.8410), "BNE": (-27.3842, 153.1175),
    "AKL": (-37.0082, 174.7850), "JNB": (-26.1367, 28.2411), "CPT": (-33.9715, 18.6021),
    "CAI": (30.1219, 31.4056),
}

AIRPORT_COORDS_CACHE: dict[str, tuple[float, float]] = dict(POPULAR_AIRPORTS)

BROWSER_HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36",
    "Accept": "application/json, text/plain, */*",
    "Accept-Language": "en-US,en;q=0.9",
}


def heading_to_cardinal(deg: float | int | None) -> str:
    """Converts heading in degrees to compass cardinal direction."""
    if deg is None:
        return "--"
    try:
        val = int((float(deg) / 22.5) + 0.5) % 16
        directions = [
            "N", "NNE", "NE", "ENE", "E", "ESE", "SE", "SSE",
            "S", "SSW", "SW", "WSW", "W", "WNW", "NW", "NNW"
        ]
        return directions[val]
    except (ValueError, TypeError):
        return "--"


def haversine_distance_nm(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    """Calculates great-circle distance between two coordinates in Nautical Miles."""
    r_nm = 3440.065
    phi1, phi2 = math.radians(lat1), math.radians(lat2)
    dphi = math.radians(lat2 - lat1)
    dlambda = math.radians(lon2 - lon1)
    a = math.sin(dphi / 2.0) ** 2 + math.cos(phi1) * math.cos(phi2) * math.sin(dlambda / 2.0) ** 2
    c = 2.0 * math.atan2(math.sqrt(a), math.sqrt(1.0 - a))
    return r_nm * c


def get_airport_coords(code: str | None) -> tuple[float, float] | None:
    """Resolves airport coordinates using in-memory registry or Flightradar24 airport search."""
    if not code:
        return None
    clean_code = code.strip().upper()
    if clean_code in AIRPORT_COORDS_CACHE:
        return AIRPORT_COORDS_CACHE[clean_code]
    try:
        results = fetch_flightradar24_search(clean_code)
        for r in results:
            if r.get("type") == "airport" and "detail" in r:
                d = r["detail"]
                if "lat" in d and "lon" in d:
                    coords = (float(d["lat"]), float(d["lon"]))
                    AIRPORT_COORDS_CACHE[clean_code] = coords
                    return coords
    except Exception:
        pass
    return None


def calculate_predicted_landing(
    current_lat: float | None,
    current_lon: float | None,
    speed_kts: float | int | None,
    dest_code: str | None,
    altitude_ft: float | int | None = None,
    on_ground: bool = False,
) -> tuple[int | None, str]:
    """Calculates predicted minutes until touchdown and formatted ETA string."""
    if on_ground:
        return 0, "Landed / On Ground"

    if current_lat is None or current_lon is None:
        return None, "Triangulating sector"

    if not dest_code or str(dest_code).upper() in ("UNKNOWN", "N/A", "--"):
        return None, "En route (Destination unfiled)"

    dest_coords = get_airport_coords(str(dest_code))
    if not dest_coords:
        return None, "Calculating approach"

    dest_lat, dest_lon = dest_coords
    dist_nm = haversine_distance_nm(current_lat, current_lon, dest_lat, dest_lon)

    spd = float(speed_kts) if speed_kts else 0
    if spd < 40 and (altitude_ft is None or altitude_ft < 150):
        return 0, "Landed / On Ground"

    # Effective speed cap to avoid divide-by-zero or taxi anomalies
    effective_spd = max(spd, 140.0)
    hours = dist_nm / effective_spd
    minutes = int(round(hours * 60.0))

    # Add 12 minutes standard approach & descent pattern buffer if high cruising
    if altitude_ft and altitude_ft > 18000 and dist_nm > 120:
        minutes += 12
    elif dist_nm < 30:
        minutes = max(3, minutes)

    now_utc = datetime.now(timezone.utc)
    eta_time = now_utc + timedelta(minutes=minutes)
    time_str = eta_time.strftime("%H:%M")

    if minutes < 60:
        eta_desc = f"{minutes} min (ETA ~{time_str} UTC)"
    else:
        h = minutes // 60
        m = minutes % 60
        eta_desc = f"{minutes} min ({h}h {m:02d}m - ~{time_str} UTC)"

    return minutes, eta_desc


def format_flight_telemetry(flight_data: dict[str, Any]) -> str:
    """Formats structured flight telemetry into a clinical Aperture Science HUD ASCII card."""
    callsign = flight_data.get("callsign", "N/A")
    f_num = flight_data.get("flight_number") or callsign
    display_title = f"{callsign} ({f_num})" if f_num and f_num != callsign else callsign

    orig = flight_data.get("origin", "Unknown")
    dest = flight_data.get("dest", "Unknown")
    route = f"{orig} -> {dest}"

    alt = flight_data.get("altitude_ft")
    if alt is not None:
        try:
            alt_int = int(round(float(alt)))
            alt_m = int(round(alt_int * 0.3048))
            alt_str = f"{alt_int:,} FT ({alt_m:,} m)"
        except (ValueError, TypeError):
            alt_str = f"{alt} FT"
    else:
        alt_str = "Unavailable"

    spd = flight_data.get("speed_kts")
    kmh = flight_data.get("speed_kmh")
    if spd is not None:
        try:
            spd_int = int(round(float(spd)))
            if kmh is not None:
                kmh_int = int(round(float(kmh)))
                spd_str = f"{spd_int} KTS ({kmh_int} km/h)"
            else:
                kmh_int = int(round(spd_int * 1.852))
                spd_str = f"{spd_int} KTS ({kmh_int} km/h)"
        except (ValueError, TypeError):
            spd_str = f"{spd} KTS"
    else:
        spd_str = "Unavailable"

    hdg = flight_data.get("heading")
    if hdg is not None:
        try:
            hdg_int = int(round(float(hdg)))
            cardinal = heading_to_cardinal(hdg_int)
            hdg_str = f"{hdg_int:03d}° ({cardinal})"
        except (ValueError, TypeError):
            hdg_str = str(hdg)
    else:
        hdg_str = "--"

    pred_mins = flight_data.get("predicted_minutes")
    eta_str = flight_data.get("eta_str")
    if not eta_str:
        if pred_mins is not None:
            eta_str = f"{pred_mins} min" if pred_mins > 0 else "Landed / On Ground"
        else:
            eta_str = "Calculating approach"

    model = flight_data.get("model", "Commercial Aircraft")
    reg = flight_data.get("reg") or "Standard Fleet"
    status = (flight_data.get("status") or "EN ROUTE").upper()

    lat = flight_data.get("lat")
    lon = flight_data.get("lon")
    if lat is not None and lon is not None:
        try:
            coords_str = f"{float(lat):.4f}°, {float(lon):.4f}°"
        except (ValueError, TypeError):
            coords_str = f"{lat}°, {lon}°"
    else:
        coords_str = "Sector triangulating"

    fr24_url = flight_data.get("fr24_url") or f"https://www.flightradar24.com/{callsign}"
    status_display = f"[● {status}]"

    card = (
        "+--------------------------------------------------------------------+\n"
        "|           APERTURE SCIENCE AIRSPACE RADAR TELEMETRY HUD            |\n"
        "+--------------------------------------------------------------------+\n"
        f"| Callsign / Flight : {display_title[:46]:<46} |\n"
        f"| Airspace Route    : {route[:46]:<46} |\n"
        f"| Radar Status      : {status_display[:46]:<46} |\n"
        f"| Predicted Landing : {eta_str[:46]:<46} |\n"
        f"| Aircraft Model    : {model[:46]:<46} |\n"
        f"| Registration      : {reg[:46]:<46} |\n"
        f"| Live Altitude     : {alt_str[:46]:<46} |\n"
        f"| Ground Speed      : {spd_str[:46]:<46} |\n"
        f"| Flight Heading    : {hdg_str[:46]:<46} |\n"
        f"| Coordinates       : {coords_str[:46]:<46} |\n"
        f"| Live Radar URL    : {fr24_url[:46]:<46} |\n"
        "+--------------------------------------------------------------------+"
    )
    return card


def format_flight_terminal_card(flight_data: dict[str, Any]) -> str:
    """Generates the full dual-box terminal view matching Picture 4."""
    callsign = flight_data.get("callsign", "AA100")
    header = (
        "+====================================================================+\n"
        "|    APERTURE SCIENCE AIRSPACE RADAR - REAL-TIME TELEMETRY TRACKER   |\n"
        f"| [● LIVE ADS-B FEED] Callsign: {callsign:<10}  Auto-refresh: every 3.5s|\n"
        "| Press Ctrl+C at any time to return to GLaDOS-CLI console           |\n"
        "+====================================================================+"
    )
    hud = format_flight_telemetry(flight_data)
    return header + "\n" + hud


def get_tracked_flight() -> dict[str, Any] | None:
    """Returns the most recent tracked flight telemetry from memory or disk."""
    flight_res = None
    try:
        from ui.state import ui_state
        state = ui_state.get_state()
        if state and state.get("tracked_flight"):
            flight_res = state["tracked_flight"]
    except Exception:
        pass

    if not flight_res and TRACKED_FLIGHT_FILE.exists():
        try:
            with open(TRACKED_FLIGHT_FILE, "r", encoding="utf-8") as f:
                data = json.load(f)
                if isinstance(data, dict) and data.get("callsign"):
                    flight_res = data
        except Exception as e:
            logger.debug(f"Failed to read tracked flight from disk: {e}")

    if flight_res:
        flight_res["hud_card"] = format_flight_telemetry(flight_res)
        flight_res["full_terminal_card"] = format_flight_terminal_card(flight_res)
    return flight_res


def clean_flight_query(query: str) -> str:
    """Cleans user spoken query into standard flight/callsign format (e.g. 'AA 100' -> 'AA100')."""
    clean = query.strip().upper()
    for prefix in ("TRACK FLIGHT", "WHERE IS FLIGHT", "WHERE IS", "TRACK", "FLIGHT", "VOO"):
        if clean.startswith(prefix):
            clean = clean[len(prefix):].strip()
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

        # Flightradar24 sector feed index mapping:
        # 0=mode_s_hex, 1=lat, 2=lon, 3=heading, 4=altitude_ft, 5=speed_kts,
        # 8=model, 9=reg, 11=orig, 12=dest, 13=flight, 14=on_ground, 15=vspd, 16=callsign
        lat_val = plane_entry[1] if len(plane_entry) > 1 else None
        lon_val = plane_entry[2] if len(plane_entry) > 2 else None
        hdg_val = plane_entry[3] if len(plane_entry) > 3 else None
        alt_val = plane_entry[4] if len(plane_entry) > 4 else None
        spd_val = plane_entry[5] if len(plane_entry) > 5 else None

        spd_kmh = int(round(float(spd_val) * 1.852)) if spd_val is not None else None

        return {
            "lat": lat_val,
            "lon": lon_val,
            "heading": hdg_val,
            "altitude_ft": alt_val,
            "speed_kts": spd_val,
            "speed_kmh": spd_kmh,
            "model": (len(plane_entry) > 8 and plane_entry[8]) or "Aircraft",
            "reg": (len(plane_entry) > 9 and plane_entry[9]) or "Unknown",
            "origin": (len(plane_entry) > 11 and plane_entry[11]) or "Unknown",
            "dest": (len(plane_entry) > 12 and plane_entry[12]) or "Unknown",
            "flight": (len(plane_entry) > 13 and plane_entry[13]) or "Unknown",
            "on_ground": bool(len(plane_entry) > 14 and plane_entry[14]),
            "vertical_speed_fpm": plane_entry[15] if len(plane_entry) > 15 else 0,
            "callsign": (len(plane_entry) > 16 and plane_entry[16]) or "Unknown",
        }
    except Exception as e:
        logger.debug(f"Telemetry fetch error for flight {flight_id}: {e}")
        return None


def refresh_flight_data(callsign: str) -> dict[str, Any] | None:
    """Fetches real-time telemetry update for an active flight and refreshes memory and disk."""
    clean = clean_flight_query(callsign)
    if not clean:
        return None

    try:
        results = fetch_flightradar24_search(clean)
        live_matches = [r for r in results if r.get("type") == "live"]
        if not live_matches:
            return None

        match = live_matches[0]
        flight_id = match.get("id", "")
        detail = match.get("detail", {})
        lat = detail.get("lat")
        lon = detail.get("lon")

        telemetry = None
        if lat is not None and lon is not None:
            telemetry = fetch_live_sector_telemetry(lat, lon, flight_id)

        flight_num = (telemetry and telemetry.get("flight")) or detail.get("flight") or clean
        model = (telemetry and telemetry.get("model")) or detail.get("ac_type") or "Aircraft"
        orig = (telemetry and telemetry.get("origin")) or detail.get("schd_from") or "Unknown"
        dest = (telemetry and telemetry.get("dest")) or detail.get("schd_to") or "Unknown"
        alt = (telemetry and telemetry.get("altitude_ft"))
        spd = (telemetry and telemetry.get("speed_kts"))
        spd_kmh = (telemetry and telemetry.get("speed_kmh"))
        hdg = (telemetry and telemetry.get("heading"))
        reg = (telemetry and telemetry.get("reg")) or detail.get("reg") or ""

        vspd = (telemetry and telemetry.get("vertical_speed_fpm")) or 0
        if telemetry and telemetry.get("on_ground"):
            status_desc = "On ground / Taxiing"
        elif vspd > 400:
            status_desc = "Climbing"
        elif vspd < -400:
            status_desc = "Descending for approach"
        else:
            status_desc = "Cruising"

        pred_mins, eta_str = calculate_predicted_landing(
            current_lat=lat,
            current_lon=lon,
            speed_kts=spd,
            dest_code=dest,
            altitude_ft=alt,
            on_ground=bool(telemetry and telemetry.get("on_ground")),
        )

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
            "predicted_minutes": pred_mins,
            "eta_str": eta_str,
            "updated_at": time.time(),
            "fr24_url": f"https://www.flightradar24.com/{clean}"
        }

        try:
            from ui.state import ui_state
            ui_state.update(tracked_flight=flight_data)
        except Exception:
            pass

        try:
            TRACKED_FLIGHT_FILE.parent.mkdir(parents=True, exist_ok=True)
            with open(TRACKED_FLIGHT_FILE, "w", encoding="utf-8") as f:
                json.dump(flight_data, f, indent=2)
        except Exception as e:
            logger.debug(f"Failed to persist refreshed flight: {e}")

        return flight_data
    except Exception as e:
        logger.debug(f"Error refreshing flight {clean}: {e}")
        return None


# Global background flight updater daemon
_tracker_lock = threading.Lock()
_active_tracker_thread: threading.Thread | None = None
_stop_tracker_flag = threading.Event()


def _flight_auto_updater_worker() -> None:
    """Background worker daemon that polls active flight telemetry every 10 seconds for real-time tracking."""
    while not _stop_tracker_flag.wait(10):
        try:
            flight = get_tracked_flight()
            if not flight:
                continue
            callsign = flight.get("callsign")
            if not callsign:
                continue

            # If flight is already landed, reduce polling
            if flight.get("status") in ("On ground / Taxiing", "Landed / On Ground"):
                time.sleep(20)
                continue

            refresh_flight_data(callsign)
        except Exception as e:
            logger.debug(f"Auto-updater tick error: {e}")


def ensure_flight_auto_updater() -> None:
    """Spawns the background auto-updater thread if not already running."""
    global _active_tracker_thread
    with _tracker_lock:
        if _active_tracker_thread is None or not _active_tracker_thread.is_alive():
            _stop_tracker_flag.clear()
            _active_tracker_thread = threading.Thread(
                target=_flight_auto_updater_worker,
                daemon=True,
                name="FlightAutoUpdater",
            )
            _active_tracker_thread.start()


@register_tool(
    name="track_flight",
    description="Tracks a live aircraft using Flightradar24 real-time telemetry (altitude, speed, route, aircraft type, predicted minutes until landing, and status).",
    sensitive=False,
)
def track_flight(flight_query: str, open_browser: bool = False, **kwargs) -> Tuple[bool, str]:
    """
    Looks up live flight telemetry from Flightradar24 and initializes auto-updating tracking.
    """
    clean = clean_flight_query(flight_query)
    if not clean:
        return False, "Please specify a flight number to track (e.g. DL450, AA100, TAP123)."

    try:
        flight_data = refresh_flight_data(clean)
        if not flight_data:
            # Fallback search check for archive info
            results = fetch_flightradar24_search(clean)
            if results:
                first = results[0]
                label = first.get("label", clean)
                return False, f"Flight '{clean}' ({label}) was found in archives, but is not currently airborne on live radar."
            return False, f"No active flight matching '{clean}' could be located on Flightradar24."

        # Start auto-updater daemon
        ensure_flight_auto_updater()

        flight_num = flight_data.get("flight_number") or clean
        model = flight_data.get("model") or "Aircraft"
        orig = flight_data.get("origin") or "Unknown"
        dest = flight_data.get("dest") or "Unknown"
        status_desc = flight_data.get("status") or "Cruising"
        alt = flight_data.get("altitude_ft")
        spd = flight_data.get("speed_kts")
        spd_kmh = flight_data.get("speed_kmh")
        pred_mins = flight_data.get("predicted_minutes")

        alt_str = f"{int(round(float(alt))):,} feet" if alt is not None else "Altitude unavailable"
        if spd is not None:
            spd_val = int(round(float(spd)))
            kmh_val = int(round(float(spd_kmh))) if spd_kmh is not None else int(round(spd_val * 1.852))
            spd_str = f"{spd_val} knots ({kmh_val} km/h)"
        else:
            spd_str = "Speed unavailable"

        eta_speech = ""
        if pred_mins is not None and pred_mins > 0:
            if pred_mins < 60:
                eta_speech = f" Predicted landing in approximately {pred_mins} minutes."
            else:
                h = pred_mins // 60
                m = pred_mins % 60
                eta_speech = f" Predicted landing in approximately {h} hours {m} minutes."
        elif pred_mins == 0:
            eta_speech = " The aircraft is currently on the ground."

        speech = (
            f"Flight {flight_num}, an {model} en route from {orig} to {dest}, is currently {status_desc} "
            f"at {alt_str} at {spd_str}.{eta_speech}"
        )

        hud_card = format_flight_telemetry(flight_data)
        full_message = f"{speech}\n\n{hud_card}"

        if open_browser:
            webbrowser.open(f"https://www.flightradar24.com/{clean}")

        return True, full_message
    except Exception as e:
        logger.exception(f"Failed to track flight '{flight_query}': {e}")
        return False, f"Aperture Science airspace radar telemetry failed: {e}"


@register_tool(
    name="get_tracked_flight_info",
    description="Retrieves the real-time flight telemetry HUD (Callsign, Route, Altitude, Speed, Heading, Model, Registration, Radar Status, Predicted Landing, and FR24 URL) for the currently tracked flight.",
    sensitive=False,
)
def get_tracked_flight_info(auto_refresh: bool = True, **kwargs) -> Tuple[bool, str]:
    """Provides complete radar telemetry HUD for the currently tracked flight, auto-updating if needed."""
    flight = get_tracked_flight()
    if not flight:
        return False, "No active flight is currently tracked on radar. Specify a flight number (e.g. 'track flight AA100' or 'DL450') to acquire telemetry."

    callsign = flight.get("callsign")
    last_updated = flight.get("updated_at", 0)

    # Auto-update if telemetry is older than 10 seconds
    if auto_refresh and callsign and (time.time() - last_updated > 10):
        refreshed = refresh_flight_data(callsign)
        if refreshed:
            flight = refreshed

    # Ensure background updater daemon is active
    ensure_flight_auto_updater()

    hud = format_flight_telemetry(flight)
    callsign = flight.get("callsign", "Target")
    status = flight.get("status", "Active")
    pred_mins = flight.get("predicted_minutes")
    eta_text = flight.get("eta_str")
    eta_line = f" Landing in {eta_text}." if eta_text and "min" in eta_text else ""
    summary = f"Aperture Science radar tracking active for {callsign} ({status}).{eta_line}\n\n{hud}"
    return True, summary


def run_dynamic_flight_tracker(
    flight_query: str | None = None,
    interval: float = 3.5,
    max_ticks: int | None = None,
) -> None:
    """
    Enters an interactive, dynamic real-time radar tracker in the terminal.
    Continuously polls and redraws telemetry (altitude, speed, heading, coordinates,
    predicted minutes until touchdown) in-place without requiring manual interaction.
    Pressing Ctrl+C exits cleanly back to the GLaDOS-CLI prompt.
    """
    if hasattr(sys.stdout, "reconfigure"):
        try:
            sys.stdout.reconfigure(encoding="utf-8", errors="replace")
        except Exception:
            pass

    if os.name == "nt":
        try:
            os.system("")  # Enable VT100 ANSI processing in Windows console
        except Exception:
            pass

    flight = None
    if flight_query:
        clean = clean_flight_query(flight_query)
        if clean:
            flight = refresh_flight_data(clean)
            if not flight:
                track_flight(clean, open_browser=False)
                flight = get_tracked_flight()

    if not flight:
        flight = get_tracked_flight()

    if not flight or not flight.get("callsign"):
        print("\n[!] No active flight is currently tracked on radar.")
        print("    Specify a flight number to track (e.g. 'live track SAT442' or 'track AEA185').\n")
        return

    callsign = flight.get("callsign", "Target")
    flight_num = flight.get("flight_number") or callsign
    spinner = ["◐", "◓", "◑", "◒"]
    tick = 0

    ensure_flight_auto_updater()

    print(f"\n[*] Initializing Aperture Science Dynamic Radar Tracker for {callsign}...")
    time.sleep(0.4)

    try:
        while True:
            # Poll live telemetry from Flightradar24
            refreshed = refresh_flight_data(callsign)
            if refreshed:
                flight = refreshed

            hud = format_flight_telemetry(flight)
            spin_char = spinner[tick % len(spinner)]
            tick += 1
            now_utc = datetime.now(timezone.utc).strftime("%H:%M:%S UTC")

            header = (
                "+====================================================================+\n"
                f"|    APERTURE SCIENCE AIRSPACE RADAR - REAL-TIME TELEMETRY TRACKER   |\n"
                f"| [{spin_char} LIVE ADS-B FEED] Callsign: {callsign:<10}  Auto-refresh: every {interval:.1f}s  |\n"
                "| Press Ctrl+C at any time to return to GLaDOS-CLI console           |\n"
                "+====================================================================+"
            )
            footer = (
                f"[Telemetry Synchronized: {now_utc}] Tracking {callsign} ({flight_num}) on active radar.\n"
                f"[Press Ctrl+C to exit dynamic tracker and return to GLaDOS-CLI]"
            )

            # Smooth in-place screen refresh using ANSI VT100 codes
            sys.stdout.write("\033[H\033[J")
            sys.stdout.write(header + "\n" + hud + "\n" + footer + "\n")
            sys.stdout.flush()

            if max_ticks and tick >= max_ticks:
                break

            # Responsive wait loop so Ctrl+C breaks immediately
            end_time = time.time() + interval
            while time.time() < end_time:
                time.sleep(0.1)

    except KeyboardInterrupt:
        sys.stdout.write("\n\n[*] Exited dynamic radar tracker. Returning to GLaDOS-CLI console.\n\n")
        sys.stdout.flush()


# Auto-start real-time updater daemon if an active flight was already being tracked
try:
    _initial_flight = get_tracked_flight()
    if _initial_flight and _initial_flight.get("callsign"):
        ensure_flight_auto_updater()
except Exception:
    pass
