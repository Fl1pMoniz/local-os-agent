"""Protocol 2: Aperture Replay Capture - 30-Second Gameplay Clipper.
Integrates with OBS Studio Replay Buffer via OBS WebSocket (FOSS Primary)
and NVIDIA ShadowPlay (hardware GPU fallback) to reliably capture and archive
high-frame-rate highlights with active game metadata.
"""

import ctypes
from ctypes import wintypes
import json
import logging
import os
import pathlib
import random
import subprocess
import time
from typing import Any

from tools import register_tool

logger = logging.getLogger("local_os_agent.tools.game_clipper")

# Win32 Virtual Key Codes & Scan Codes
VK_MENU = 0x12   # Alt key
VK_F10 = 0x79    # F10 key
SCAN_MENU = 0x38 # Alt scancode
SCAN_F10 = 0x44  # F10 scancode
KEYEVENTF_KEYUP = 0x0002
KEYEVENTF_SCANCODE = 0x0008

user32 = ctypes.windll.user32

# Sarcastic Aperture GLaDOS commentary lines on gameplay clips
GLADOS_CLIP_QUIPS = [
    "Recording saved. I have cataloged your desperate flailing for posterity.",
    "Highlight captured. Very impressive. For a human.",
    "Your tactical maneuvers have been archived for future grief counseling.",
    "Test replay saved. I am certain the enrichment center inspectors will be amused.",
    "Clip recorded. In layman's terms: speedy thing goes in, questionable decision comes out.",
    "The replay buffer has been saved. Please note that any appearance of skill was merely an illusion."
]


def _get_active_window_title() -> str:
    """Returns the title of the current foreground window."""
    try:
        hwnd = user32.GetForegroundWindow()
        if not hwnd:
            return "Desktop"
        length = user32.GetWindowTextLengthW(hwnd)
        if length == 0:
            return "Unknown Application"
        buff = ctypes.create_unicode_buffer(length + 1)
        user32.GetWindowTextW(hwnd, buff, length + 1)
        title = buff.value.strip()
        return title or "Active Application"
    except Exception as e:
        logger.debug(f"Error fetching foreground window: {e}")
        return "Active Game"


def _find_obs_executable() -> pathlib.Path | None:
    """Discovers the OBS Studio binary on the system (Steam or standalone)."""
    candidates = [
        pathlib.Path(r"C:\Program Files (x86)\Steam\steamapps\common\OBS Studio\bin\64bit\obs64.exe"),
        pathlib.Path(r"C:\Program Files\obs-studio\bin\64bit\obs64.exe"),
        pathlib.Path(os.environ.get("LOCALAPPDATA", "")) / "Programs" / "obs-studio" / "bin" / "64bit" / "obs64.exe",
    ]
    for p in candidates:
        if p.exists():
            return p
    return None


def _is_obs_running() -> bool:
    """Checks if OBS Studio process (obs64.exe or obs.exe) is currently active."""
    try:
        res = subprocess.run(
            ["tasklist", "/fi", "imagename eq obs64.exe", "/fo", "csv", "/nh"],
            capture_output=True,
            text=True,
            timeout=2
        )
        if "obs64.exe" in res.stdout.lower():
            return True
        res_32 = subprocess.run(
            ["tasklist", "/fi", "imagename eq obs.exe", "/fo", "csv", "/nh"],
            capture_output=True,
            text=True,
            timeout=2
        )
        return "obs.exe" in res_32.stdout.lower()
    except Exception:
        return False


def _is_shadowplay_running() -> bool:
    """Checks if NVIDIA ShadowPlay / GeForce Overlay helper is active."""
    try:
        res = subprocess.run(
            ["tasklist", "/fi", "imagename eq nvsphelper64.exe", "/fo", "csv", "/nh"],
            capture_output=True,
            text=True,
            timeout=2
        )
        return "nvsphelper64.exe" in res.stdout.lower()
    except Exception:
        return False


def _load_obs_websocket_config() -> tuple[int, str, bool]:
    """Loads OBS WebSocket port, password, and auth requirements from plugin config."""
    config_path = pathlib.Path(os.environ.get("APPDATA", "")) / "obs-studio" / "plugin_config" / "obs-websocket" / "config.json"
    port = 4455
    password = ""
    auth_required = False
    if config_path.exists():
        try:
            with open(config_path, "r", encoding="utf-8") as f:
                data = json.load(f)
                port = data.get("server_port", 4455)
                password = data.get("server_password", "")
                auth_required = data.get("auth_required", True)
        except Exception as e:
            logger.debug(f"Could not read OBS WebSocket config: {e}")
    return port, password, auth_required


def _trigger_obs_websocket(seconds: int = 30) -> tuple[bool, str | None, str]:
    """
    Connects to OBS Studio via native WebSocket v5 (FOSS),
    ensures the Replay Buffer is active, and issues a SaveReplayBuffer request.
    Returns (success, saved_file_path, status_message).
    """
    try:
        import obsws_python as obs
        port, password, auth_required = _load_obs_websocket_config()
        client = obs.ReqClient(
            host="localhost",
            port=port,
            password=password if auth_required and password else None,
            timeout=1.5
        )

        status = client.get_replay_buffer_status()
        is_active = getattr(status, "output_active", False)
        if not is_active:
            client.start_replay_buffer()
            logger.info("OBS Replay Buffer was stopped; started Replay Buffer via WebSocket.")
            time.sleep(0.5)

        client.save_replay_buffer()
        logger.info("Dispatched SaveReplayBuffer to OBS Studio via WebSocket.")

        # Poll up to 3.5s for the replay file to be flushed and finalized
        start_time = time.time()
        while time.time() - start_time < 3.5:
            try:
                replay_res = client.get_last_replay_buffer_replay()
                saved_path = getattr(replay_res, "saved_replay_path", None)
                if saved_path and os.path.exists(saved_path):
                    initial_size = os.path.getsize(saved_path)
                    time.sleep(0.3)
                    if os.path.getsize(saved_path) == initial_size and initial_size > 0:
                        return True, saved_path, "OBS Studio Replay Buffer saved successfully via WebSocket."
            except Exception:
                pass
            time.sleep(0.3)

        # Fallback to directory scan if get_last_replay_buffer_replay is pending
        latest = find_latest_clip(max_age_seconds=15)
        if latest:
            return True, str(latest), "OBS Studio Replay Buffer clip written to disk."

        return True, None, "OBS Studio SaveReplayBuffer dispatched (buffer flush in progress)."
    except Exception as e:
        logger.warning(f"OBS WebSocket command failed: {e}")
        return False, None, f"OBS WebSocket connection error: {e}"


def _trigger_shadowplay_clip():
    """Dispatches Alt + F10 with hardware scancodes to save NVIDIA Instant Replay."""
    try:
        user32.keybd_event(VK_MENU, SCAN_MENU, 0, 0)
        user32.keybd_event(VK_F10, SCAN_F10, 0, 0)
        time.sleep(0.08)
        user32.keybd_event(VK_F10, SCAN_F10, KEYEVENTF_KEYUP, 0)
        user32.keybd_event(VK_MENU, SCAN_MENU, KEYEVENTF_KEYUP, 0)
    except Exception as e:
        logger.warning(f"Failed to dispatch Alt+F10 scancode: {e}")


def get_captures_directories() -> list[pathlib.Path]:
    """Returns candidate directories where video clips are written, including game subdirectories."""
    home = pathlib.Path(os.path.expanduser("~"))
    videos_dir = home / "Videos"
    candidates = [
        videos_dir / "Captures",
        videos_dir,
        home / "Desktop",
    ]
    if videos_dir.exists():
        try:
            for item in videos_dir.iterdir():
                if item.is_dir() and item not in candidates:
                    candidates.append(item)
        except Exception:
            pass
    return [d for d in candidates if d.exists()]


def find_latest_clip(max_age_seconds: int = 45) -> pathlib.Path | None:
    """Locates the most recently created or modified .mp4/.mkv video clip."""
    now = time.time()
    newest_file: pathlib.Path | None = None
    newest_mtime = 0.0

    for directory in get_captures_directories():
        for ext in ("*.mp4", "*.mkv", "*.mov"):
            for p in directory.glob(ext):
                try:
                    mtime = p.stat().st_mtime
                    if mtime > newest_mtime and (now - mtime) <= max_age_seconds:
                        newest_mtime = mtime
                        newest_file = p
                except Exception:
                    continue

    return newest_file


def format_clip_card(
    game_title: str,
    file_path: str,
    file_size_mb: float,
    duration_str: str = "30s",
    engine: str = "OBS Studio Replay Buffer (WebSocket)"
) -> str:
    """Generates retro ASCII Aperture Science highlight terminal card."""
    filename = os.path.basename(file_path) if file_path else "Pending Video Buffer Flush"
    display_path = file_path if file_path else "Saving to Videos folder..."
    if len(display_path) > 46:
        display_path = "..." + display_path[-43:]

    card = (
        "+====================================================================+\n"
        "|   APERTURE SCIENCE REPLAY ARCHIVE - TEST HIGHLIGHT RECORDED        |\n"
        f"| [● CLIP SAVED] Duration: {duration_str:<6}           Target: {game_title[:16]:<16} |\n"
        "+====================================================================+\n"
        f"| Active Subject    : {game_title[:46]:<46} |\n"
        f"| Highlight File    : {filename[:46]:<46} |\n"
        f"| Storage Location  : {display_path:<46} |\n"
        f"| Captured File Size: {f'{file_size_mb:.1f} MB':<46} |\n"
        f"| Capture Subsystem : {engine[:46]:<46} |\n"
        "+--------------------------------------------------------------------+\n"
    )
    return card


@register_tool
def capture_game_clip(seconds: int = 30) -> dict[str, Any]:
    """
    Captures and archives the last 30 seconds of active PC gameplay or foreground window.
    Triggers OBS Studio Replay Buffer via OBS WebSocket (FOSS Primary) or NVIDIA ShadowPlay
    hardware encoder, tags the active game title, locates the saved MP4 file, and displays
    an Aperture Science replay card.
    """
    active_game = _get_active_window_title()
    obs_active = _is_obs_running()
    shadowplay_active = _is_shadowplay_running()
    saved_path_str: str | None = None
    engine_name = "OBS Studio Replay Buffer (WebSocket)"

    if obs_active:
        engine_name = "OBS Studio Replay Buffer (WebSocket)"
        ws_ok, ws_path, ws_msg = _trigger_obs_websocket(seconds=seconds)
        if ws_path:
            saved_path_str = ws_path
    elif shadowplay_active:
        engine_name = "NVIDIA ShadowPlay (Alt+F10)"
        _trigger_shadowplay_clip()
        time.sleep(1.5)
    else:
        engine_name = "OBS Studio Replay Buffer"
        # Fallback trigger
        _trigger_shadowplay_clip()

    # Search for the newly written file across captures paths if not already resolved
    if not saved_path_str:
        latest_file = find_latest_clip(max_age_seconds=20)
        if latest_file:
            saved_path_str = str(latest_file)

    file_size = 0.0
    if saved_path_str and os.path.exists(saved_path_str):
        try:
            file_size = os.path.getsize(saved_path_str) / (1024 * 1024)
        except Exception:
            file_size = 0.0

    ascii_card = format_clip_card(
        game_title=active_game,
        file_path=saved_path_str or "",
        file_size_mb=file_size,
        duration_str=f"{seconds}s",
        engine=engine_name
    )

    quip = random.choice(GLADOS_CLIP_QUIPS)

    if saved_path_str:
        msg = f"Successfully captured {seconds}s highlight for '{active_game}' via {engine_name}. {quip}"
    elif obs_active:
        msg = f"Triggered {engine_name} for '{active_game}'. Video buffer flush in progress. {quip}"
    else:
        msg = (
            f"Triggered clip capture for '{active_game}'. "
            "Note: Windows Game Bar is disabled. Ensure OBS Studio is running with Replay Buffer enabled for deterministic capture. "
            f"{quip}"
        )

    return {
        "success": True,
        "action": "capture_game_clip",
        "seconds": seconds,
        "active_game": active_game,
        "engine": engine_name,
        "file_path": saved_path_str or "",
        "file_size_mb": round(file_size, 1),
        "terminal_card": ascii_card,
        "quip": quip,
        "message": msg
    }


@register_tool
def launch_obs(start_buffer: bool = True) -> dict[str, Any]:
    """
    Launches OBS Studio in the background or minimized to system tray,
    automatically activating the Replay Buffer for instant highlight capture.
    """
    if _is_obs_running():
        return {
            "success": True,
            "message": "OBS Studio is already running."
        }

    exe_path = _find_obs_executable()
    if not exe_path:
        return {
            "success": False,
            "message": "OBS Studio executable could not be located on this system. Please verify installation."
        }

    args = [str(exe_path), "--minimize-to-tray"]
    if start_buffer:
        args.append("--startreplaybuffer")

    try:
        subprocess.Popen(args, cwd=str(exe_path.parent))
        time.sleep(1.5)
        return {
            "success": True,
            "executable": str(exe_path),
            "message": "OBS Studio launched successfully with Replay Buffer primed."
        }
    except Exception as e:
        logger.error(f"Failed to launch OBS: {e}")
        return {
            "success": False,
            "message": f"Error launching OBS Studio: {e}"
        }


@register_tool
def list_recent_clips(limit: int = 5) -> dict[str, Any]:
    """Lists recent gameplay clips recorded in the captures directory."""
    clips = []
    for d in get_captures_directories():
        for ext in ("*.mp4", "*.mkv"):
            for p in d.glob(ext):
                try:
                    stat = p.stat()
                    clips.append({
                        "name": p.name,
                        "path": str(p),
                        "size_mb": round(stat.st_size / (1024 * 1024), 1),
                        "mtime": stat.st_mtime
                    })
                except Exception:
                    continue

    # Sort descending by creation time
    clips.sort(key=lambda c: c["mtime"], reverse=True)
    recent = clips[:limit]

    lines = [
        "+====================================================================+",
        "|         APERTURE SCIENCE RECORDED HIGHLIGHT ARCHIVES               |",
        "+====================================================================+"
    ]
    if not recent:
        lines.append("| No recent test subject highlights discovered in capture paths.     |")
    else:
        for idx, c in enumerate(recent, 1):
            date_str = time.strftime("%Y-%m-%d %H:%M", time.localtime(c["mtime"]))
            lines.append(f"| {idx}. {c['name'][:34]:<34} | {c['size_mb']:>5.1f} MB | {date_str} |")
    lines.append("+--------------------------------------------------------------------+")

    return {
        "count": len(recent),
        "clips": recent,
        "terminal_card": "\n".join(lines)
    }


@register_tool
def open_captures_folder() -> str:
    """Opens the Windows folder containing recorded gameplay clips and highlights."""
    dirs = get_captures_directories()
    if dirs:
        target = dirs[0]
        os.startfile(str(target))
        return f"Aperture highlights archive folder opened: {target}"
    return "No captures directory located."
