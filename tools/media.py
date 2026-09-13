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


def play_youtube(query: str, music: bool = False, **kwargs) -> Tuple[bool, str]:
    """
    Opens a YouTube or YouTube Music search in the default browser.
    If music=True or query contains 'youtube music', searches YouTube Music.
    """
    try:
        if not query or not str(query).strip():
            return False, "Query cannot be empty."

        query_clean = str(query).strip()

        # Check if YouTube Music was requested
        is_music = bool(music) or ("youtube music" in query_clean.lower()) or ("music.youtube" in query_clean.lower())

        # Clean query of common prefix fluff
        clean_text = query_clean
        for prefix in ("youtube music", "youtube", "play on youtube music", "play on youtube", "search youtube for", "search for", "play"):
            if clean_text.lower().startswith(prefix):
                clean_text = clean_text[len(prefix):].strip()
        clean_text = clean_text.strip(" :\"'")
        if not clean_text:
            clean_text = query_clean

        if "youtube.com" in query_clean or "youtu.be" in query_clean:
            url = query_clean
            if not url.startswith("http://") and not url.startswith("https://"):
                url = "https://" + url
        elif is_music:
            encoded_query = urllib.parse.quote_plus(clean_text)
            url = f"https://music.youtube.com/search?q={encoded_query}"
        else:
            encoded_query = urllib.parse.quote_plus(clean_text)
            url = f"https://www.youtube.com/results?search_query={encoded_query}"

        webbrowser.open(url)
        service_name = "YouTube Music" if is_music else "YouTube"
        return True, f"Opened {service_name} search for '{clean_text}'."
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
    if not action or not str(action).strip():
        return False, "Media action cannot be empty."

    action_normalized = str(action).lower().strip().replace("-", "_").replace(" ", "_")

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
            # If a GLaDOS song is playing, pause/stop it
            try:
                from tools.songs import is_song_playing, stop_song
                if is_song_playing() and resolved_action in ("play_pause", "stop"):
                    stop_song()
                    return True, "Stopped GLaDOS song playback."
            except Exception:
                pass

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

