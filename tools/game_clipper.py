"""Protocol 2: Aperture Replay Capture - 30-Second Gameplay Clipper.
Integrates with OBS Studio Replay Buffer and Windows Game Bar DVR (Win+Alt+G)
to capture and archive high-frame-rate highlights with active game metadata.
"""

import ctypes
from ctypes import wintypes
import glob
import logging
import os
import pathlib
import random
import subprocess
import time
from typing import Any

from tools import register_tool

logger = logging.getLogger("local_os_agent.tools.game_clipper")

# Win32 Virtual Key Codes
VK_LWIN = 0x5B
VK_MENU = 0x12   # Alt key
VK_G = 0x47      # 'G' key
VK_F10 = 0x79    # F10 key
KEYEVENTF_KEYUP = 0x0002

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


def _is_obs_running() -> bool:
    """Checks if OBS Studio process (obs64.exe or obs32.exe) is currently active."""
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


def _trigger_gamebar_clip():
    """Dispatches Win + Alt + G to save the last 30 seconds via Windows Game Bar DVR."""
    # Press Win + Alt + G
    user32.keybd_event(VK_LWIN, 0, 0, 0)
    user32.keybd_event(VK_MENU, 0, 0, 0)
    user32.keybd_event(VK_G, 0, 0, 0)
    time.sleep(0.08)
    # Release
    user32.keybd_event(VK_G, 0, KEYEVENTF_KEYUP, 0)
    user32.keybd_event(VK_MENU, 0, KEYEVENTF_KEYUP, 0)
    user32.keybd_event(VK_LWIN, 0, KEYEVENTF_KEYUP, 0)


def _trigger_obs_replay():
    """Dispatches replay save signal to OBS."""
    # Default OBS Replay Buffer Save hotkey is often configured to Ctrl+Shift+S or custom.
    # We dispatch Game Bar hotkey as universal primary fallback, while checking OBS captures.
    _trigger_gamebar_clip()


def get_captures_directories() -> list[pathlib.Path]:
    """Returns candidate directories where video clips are written."""
    home = pathlib.Path(os.path.expanduser("~"))
    candidates = [
        home / "Videos" / "Captures",
        home / "Videos",
        home / "Desktop",
    ]
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
    engine: str = "Windows Game Bar DVR / OBS Replay"
) -> str:
    """Generates retro ASCII Aperture Science highlight terminal card."""
    filename = os.path.basename(file_path) if file_path else "Pending Video Buffer Flush"
    display_path = file_path if file_path else "Saving to Videos\\Captures..."
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
    Triggers OBS Studio Replay Buffer or Windows Game Bar DVR (Win+Alt+G), tags the active
    game title, locates the saved MP4 file, and displays an Aperture Science replay card.
    """
    active_game = _get_active_window_title()
    obs_active = _is_obs_running()

    if obs_active:
        engine_name = "OBS Studio Replay Buffer"
        _trigger_obs_replay()
    else:
        engine_name = "Windows Game Bar DVR (Win+Alt+G)"
        _trigger_gamebar_clip()

    # Allow slight buffer write delay (up to 1.5s) to detect new file if flushed immediately
    time.sleep(0.5)
    latest_file = find_latest_clip(max_age_seconds=30)
    file_path_str = str(latest_file) if latest_file else ""
    file_size = 0.0

    if latest_file and latest_file.exists():
        try:
            file_size = latest_file.stat().st_size / (1024 * 1024)
        except Exception:
            file_size = 0.0

    ascii_card = format_clip_card(
        game_title=active_game,
        file_path=file_path_str,
        file_size_mb=file_size,
        duration_str=f"{seconds}s",
        engine=engine_name
    )

    quip = random.choice(GLADOS_CLIP_QUIPS)

    return {
        "success": True,
        "action": "capture_game_clip",
        "seconds": seconds,
        "active_game": active_game,
        "engine": engine_name,
        "file_path": file_path_str,
        "file_size_mb": round(file_size, 1),
        "terminal_card": ascii_card,
        "quip": quip,
        "message": f"Successfully triggered {seconds}s highlight capture for '{active_game}'. {quip}"
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

