"""Media playback and global media key control toolset."""

import logging
import platform
import urllib.parse
import webbrowser
from typing import Tuple

logger = logging.getLogger("local_os_agent.tools.media")

# Windows Virtual Key Codes for media keys
VK_MEDIA_NEXT_TRACK = 0xB0
VK_MEDIA_PREV_TRACK = 0xB1
VK_MEDIA_STOP = 0xB2
VK_MEDIA_PLAY_PAUSE = 0xB3
KEYEVENTF_KEYUP = 0x0002


def play_youtube(query: str) -> Tuple[bool, str]:
    """
    Opens a YouTube search or video in the default browser.
    If query is already a YouTube link, opens it directly; otherwise opens a search.
    """
    try:
        query_clean = query.strip()
        if not query_clean:
            return False, "Query cannot be empty."

        if "youtube.com" in query_clean or "youtu.be" in query_clean:
            url = query_clean
            if not url.startswith("http://") and not url.startswith("https://"):
                url = "https://" + url
        else:
            encoded_query = urllib.parse.quote_plus(query_clean)
            url = f"https://www.youtube.com/results?search_query={encoded_query}"

        webbrowser.open(url)
        return True, f"Opened YouTube for query '{query_clean}': {url}"
    except Exception as e:
        logger.exception("Error launching YouTube")
        return False, f"Failed to open YouTube: {e}"


def _send_windows_vk(vk_code: int) -> None:
    """Send key down and key up events for a virtual keycode on Windows."""
    import ctypes
    ctypes.windll.user32.keybd_event(vk_code, 0, 0, 0)
    ctypes.windll.user32.keybd_event(vk_code, 0, KEYEVENTF_KEYUP, 0)


def media_control(action: str) -> Tuple[bool, str]:
    """
    Simulates global media key events.
    Accepted actions: 'play_pause', 'next_track', 'prev_track'.
    """
    action_normalized = action.lower().strip().replace("-", "_").replace(" ", "_")

    # Map possible synonyms to standard actions
    action_map = {
        "play_pause": "play_pause",
        "play": "play_pause",
        "pause": "play_pause",
        "resume": "play_pause",
        "next_track": "next_track",
        "next": "next_track",
        "skip": "next_track",
        "prev_track": "prev_track",
        "previous_track": "prev_track",
        "previous": "prev_track",
        "prev": "prev_track",
    }

    resolved_action = action_map.get(action_normalized)
    if not resolved_action:
        valid_options = '["play_pause", "next_track", "prev_track"]'
        return False, f"Unknown media action '{action}'. Accepted actions: {valid_options}."

    if platform.system() == "Windows":
        try:
            if resolved_action == "play_pause":
                _send_windows_vk(VK_MEDIA_PLAY_PAUSE)
            elif resolved_action == "next_track":
                _send_windows_vk(VK_MEDIA_NEXT_TRACK)
            elif resolved_action == "prev_track":
                _send_windows_vk(VK_MEDIA_PREV_TRACK)
            return True, f"Media key '{resolved_action}' executed successfully."
        except Exception as e:
            logger.exception("Error triggering media virtual key")
            return False, f"Failed to send media key: {e}"
    else:
        # Cross-platform fallback using pyautogui if available
        try:
            import pyautogui
            if resolved_action == "play_pause":
                pyautogui.press("playpause")
            elif resolved_action == "next_track":
                pyautogui.press("nexttrack")
            elif resolved_action == "prev_track":
                pyautogui.press("prevtrack")
            return True, f"Media key '{resolved_action}' sent via pyautogui."
        except Exception as e:
            return False, f"Media control not supported on {platform.system()}: {e}"


# Register tools
from tools import register_tool

register_tool(
    name="play_youtube",
    description="Opens a YouTube search or video in the default browser.",
    sensitive=False,
)(play_youtube)

register_tool(
    name="media_control",
    description='Controls media playback. Accepted actions: "play_pause", "next_track", "prev_track".',
    sensitive=False,
)(media_control)

