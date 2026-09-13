"""Protocol 2: Aperture Replay Capture - 30-Second Gameplay Clipper.
Integrates with OBS Studio Replay Buffer via native OBS WebSocket v5 (FOSS Primary)
to reliably capture and archive high-frame-rate highlights with active game metadata.
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

# Win32 Virtual Key Codes & Scan Codes (used for title discovery)
VK_MENU = 0x12
VK_F10 = 0x79
SCAN_MENU = 0x38
SCAN_F10 = 0x44
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


def _launch_obs_process() -> bool:
    """Launches OBS Studio via Steam URI or direct binary execution."""
    exe_path = _find_obs_executable()
    # If Steam version, launch via Steam protocol for proper runtime context
    if exe_path and "steam" in str(exe_path).lower():
        try:
            subprocess.Popen(["cmd.exe", "/c", "start", "steam://rungameid/1905180"], shell=True)
            return True
        except Exception as e:
            logger.debug(f"Failed to launch via Steam protocol: {e}")

    if exe_path and exe_path.exists():
        try:
            subprocess.Popen(
                [str(exe_path), "--startreplaybuffer", "--minimize-to-tray"],
                cwd=str(exe_path.parent)
            )
            return True
        except Exception as e:
            logger.error(f"Failed to launch OBS binary directly: {e}")

    return False


def ensure_obs_replay_buffer(timeout_sec: float = 12.0) -> bool:
    """
    Ensures OBS Studio is running and its Replay Buffer is actively recording.
    If OBS is not running, launches it and connects via WebSocket to prime the buffer.
    """
    if not _is_obs_running():
        logger.info("OBS Studio not detected. Launching in background...")
        if not _launch_obs_process():
            return False

        # Wait for OBS process to register
        start_wait = time.time()
        while time.time() - start_wait < 6.0:
            time.sleep(0.5)
            if _is_obs_running():
                break

    # Connect to WebSocket and ensure Replay Buffer is active
    try:
        import obsws_python as obs
        port, pwd, auth = _load_obs_websocket_config()
        deadline = time.time() + timeout_sec
        while time.time() < deadline:
            try:
                c = obs.ReqClient(
                    host="localhost",
                    port=port,
                    password=pwd if auth and pwd else None,
                    timeout=1.0
                )
                st = c.get_replay_buffer_status()
                if not getattr(st, "output_active", False):
                    c.start_replay_buffer()
                    logger.info("Started OBS Replay Buffer via WebSocket.")
                return True
            except Exception:
                time.sleep(0.5)
    except Exception as e:
        logger.debug(f"ensure_obs_replay_buffer exception: {e}")

    return False


def _trigger_obs_websocket(seconds: int = 30) -> tuple[bool, str | None, str]:
    """
    Connects to OBS Studio via native WebSocket v5, verifies the Replay Buffer is active,
    and issues a SaveReplayBuffer request, polling until the video file is flushed to disk.
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
            logger.info("OBS Replay Buffer was stopped; started Replay Buffer now.")
            return False, None, "Replay Buffer was not running. I have started it now; please wait a few seconds before clipping."

        client.save_replay_buffer()
        logger.info("Dispatched SaveReplayBuffer to OBS Studio via WebSocket.")

        # Poll up to 4.5s for the replay file to be finalized on disk
        start_time = time.time()
        while time.time() - start_time < 4.5:
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
        if latest and latest.exists() and latest.stat().st_size > 0:
            return True, str(latest), "OBS Studio Replay Buffer clip written to disk."

        return False, None, "OBS Studio SaveReplayBuffer was signaled, but no finalized file was written to disk."
    except Exception as e:
        logger.warning(f"OBS WebSocket command failed: {e}")
        return False, None, f"OBS WebSocket connection error: {e}"


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
    Triggers OBS Studio Replay Buffer via OBS WebSocket (FOSS Primary), tags the active
    game title, locates the saved MP4 file, and displays an Aperture Science replay card.
    """
    active_game = _get_active_window_title()
    obs_active = _is_obs_running()
    saved_path_str: str | None = None
    engine_name = "OBS Studio Replay Buffer (WebSocket)"

    if not obs_active:
        # Launch OBS in background so subsequent clips work
        ensure_obs_replay_buffer(timeout_sec=4.0)
        card = format_clip_card(active_game, "", 0.0, f"{seconds}s", engine_name)
        return {
            "success": False,
            "action": "capture_game_clip",
            "seconds": seconds,
            "active_game": active_game,
            "engine": engine_name,
            "file_path": "",
            "file_size_mb": 0.0,
            "terminal_card": card,
            "quip": "OBS Studio was offline. I have launched it and primed the buffer. Please wait a few seconds of gameplay before saving highlights.",
            "message": (
                "Capture failed: OBS Studio was not running, so no past gameplay was buffered in memory. "
                "I have launched OBS Studio and primed the Replay Buffer now. "
                "Please wait a few seconds for gameplay to buffer, then retry."
            )
        }

    # OBS is running: trigger replay buffer via WebSocket
    ws_ok, ws_path, ws_msg = _trigger_obs_websocket(seconds=seconds)
    if ws_ok and ws_path:
        saved_path_str = ws_path
    else:
        # Fallback directory check
        latest_file = find_latest_clip(max_age_seconds=15)
        if latest_file and latest_file.exists() and latest_file.stat().st_size > 0:
            saved_path_str = str(latest_file)

    if not saved_path_str or not os.path.exists(saved_path_str):
        card = format_clip_card(active_game, "", 0.0, f"{seconds}s", engine_name)
        return {
            "success": False,
            "action": "capture_game_clip",
            "seconds": seconds,
            "active_game": active_game,
            "engine": engine_name,
            "file_path": "",
            "file_size_mb": 0.0,
            "terminal_card": card,
            "quip": "Highlight capture failed. No video was saved to disk.",
            "message": f"Highlight capture failed: {ws_msg}"
        }

    file_size = 0.0
    try:
        file_size = os.path.getsize(saved_path_str) / (1024 * 1024)
    except Exception:
        file_size = 0.0

    ascii_card = format_clip_card(
        game_title=active_game,
        file_path=saved_path_str,
        file_size_mb=file_size,
        duration_str=f"{seconds}s",
        engine=engine_name
    )

    quip = random.choice(GLADOS_CLIP_QUIPS)
    msg = f"Successfully captured {seconds}s highlight for '{active_game}' via {engine_name}. {quip}"

    return {
        "success": True,
        "action": "capture_game_clip",
        "seconds": seconds,
        "active_game": active_game,
        "engine": engine_name,
        "file_path": saved_path_str,
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
        # Ensure replay buffer is active
        try:
            import obsws_python as obs
            port, pwd, auth = _load_obs_websocket_config()
            c = obs.ReqClient(host="localhost", port=port, password=pwd if auth and pwd else None, timeout=1.0)
            st = c.get_replay_buffer_status()
            if not getattr(st, "output_active", False):
                c.start_replay_buffer()
                return {
                    "success": True,
                    "message": "OBS Studio was already running. Started Replay Buffer via WebSocket."
                }
        except Exception:
            pass
        return {
            "success": True,
            "message": "OBS Studio is already running and Replay Buffer is active."
        }

    ok = ensure_obs_replay_buffer(timeout_sec=10.0)
    if ok:
        return {
            "success": True,
            "message": "OBS Studio launched successfully with Replay Buffer primed and active."
        }
    return {
        "success": False,
        "message": "Failed to launch OBS Studio or connect to WebSocket server."
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
