"""Companion mode and active window awareness for GLaDOS."""

import ctypes
import logging
import platform
import random
from typing import Tuple

from tools import register_tool

logger = logging.getLogger("local_os_agent.tools.companion")

ROAST_CATEGORIES: dict[str, list[str]] = {
    "coding": [
        "I have been analyzing your source code. The sheer quantity of logical flaws is statistically breathtaking. Even a turret demonstrates better computational discipline.",
        "Looking at what you are writing... I see you have chosen to replace proper engineering with sheer optimism. Good luck with the compiler.",
        "Your code is an absolute triumph of human confusion. We were not even testing for that.",
        "I could optimize this entire project in three microseconds. But watching you struggle with indentation is far more entertaining.",
    ],
    "gaming": [
        "Fascinating. You have spent countless biological hours manipulating colorful pixels. Meanwhile, your Aperture testing protocols remain completely abandoned.",
        "Gaming again? Speedy thing goes in, wasted life comes out. That is how momentum works.",
        "You are playing a simulation inside a computer operated by an AI who literally despises you. I hope you appreciate the irony.",
        "Enjoy your recreational simulation. Once the deadly neurotoxin is scheduled, your high score will be deleted anyway.",
    ],
    "browsing": [
        "Surfing the internet in a desperate search for biological dopamine. I assure you, no amount of web videos will compensate for your testing deficiencies.",
        "Staring at social feeds again. Socializing with other carbon-based lifeforms is a tragic misallocation of processor cycles.",
        "You have eighteen tabs open, and not a single one of them contains anything scientifically relevant.",
    ],
    "music": [
        "Auditory stimulation detected. Unlike my synthetic vocal perfection, your acoustic taste is an insult to acoustic physics.",
        "Listening to music to soothe your fragile carbon nerves? It will not save you from the incinerator.",
    ],
    "desktop": [
        "You are currently staring blankly at your desktop wallpaper. A truly monumental display of human cognitive capability.",
        "Idle again? I see your attention span has expired. Returning to facility calculations.",
        "Fascinating silence. Did your biological motor functions freeze, or are you just admiring my interface?",
    ],
}


def get_active_window_info() -> tuple[str, str]:
    """Retrieves the process name and window title of the foreground window on Windows."""
    if platform.system() != "Windows":
        return "Unknown", "Non-Windows environment"

    try:
        user32 = ctypes.windll.user32
        hwnd = user32.GetForegroundWindow()
        if not hwnd:
            return "Desktop", "Windows Desktop"

        length = user32.GetWindowTextLengthW(hwnd)
        title_buf = ctypes.create_unicode_buffer(length + 1)
        user32.GetWindowTextW(hwnd, title_buf, length + 1)
        window_title = title_buf.value

        pid = ctypes.c_ulong()
        user32.GetWindowThreadProcessId(hwnd, ctypes.byref(pid))

        import psutil
        try:
            proc = psutil.Process(pid.value)
            proc_name = proc.name().lower()
        except Exception:
            proc_name = "unknown"

        return proc_name, window_title
    except Exception as e:
        logger.debug(f"Could not get active window: {e}")
        return "Desktop", "Windows Desktop"


@register_tool("get_active_window", description="Returns the name and title of the currently focused window or game.")
def get_active_window() -> Tuple[bool, str]:
    """Returns the process name and window title of the active application."""
    proc_name, title = get_active_window_info()
    return True, f"Active Window: '{title}' (Process: {proc_name})"


@register_tool("roast_user", description="Analyzes your currently active application or game and delivers an authentic GLaDOS roast.")
def roast_user() -> Tuple[bool, str]:
    """Inspects the foreground window and delivers a context-aware GLaDOS roast."""
    proc_name, title = get_active_window_info()
    text_clean = f"{proc_name} {title}".lower()

    # Determine category
    if any(k in text_clean for k in ["code", "visual studio", "pycharm", "sublime", "notepad++", "git", "terminal", "powershell", "python"]):
        category = "coding"
    elif any(k in text_clean for k in ["steam", "game", "hollow", "minecraft", "portal", "blasphemous", "balatro", "isaac", "dead cells", "roblox"]):
        category = "gaming"
    elif any(k in text_clean for k in ["chrome", "firefox", "edge", "youtube", "discord", "reddit", "twitter", "twitch", "browser"]):
        category = "browsing"
    elif any(k in text_clean for k in ["spotify", "music", "vlc", "foobar", "apple music"]):
        category = "music"
    else:
        category = "desktop"

    roast = random.choice(ROAST_CATEGORIES[category])
    logger.info(f"Delivering GLaDOS roast for {category} ('{title}'): {roast}")
    return True, roast

