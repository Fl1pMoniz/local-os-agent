"""Media playback and global media key control toolset."""

import logging
import platform
import re
import urllib.parse
import urllib.request
import webbrowser
from typing import Tuple

logger = logging.getLogger("local_os_agent.tools.media")

# Windows Virtual Key Codes for media keys
VK_MEDIA_NEXT_TRACK = 0xB0
VK_MEDIA_PREV_TRACK = 0xB1
VK_MEDIA_STOP = 0xB2
VK_MEDIA_PLAY_PAUSE = 0xB3
KEYEVENTF_KEYUP = 0x0002


def clean_youtube_query(text: str) -> str:
    """
    Strips common command wrappers (e.g. 'open the song ... and start playing it on youtube music')
    to isolate the exact song title or artist query.
    """
    s = text.strip()
    prefixes = [
        r"^(?:please\s+)?(?:directly\s+)?(?:open|play|start\s+playing|start|listen\s+to|search\s+for|search)\s+(?:the\s+|a\s+|o\s+)?(?:song|track|music|musica)?\s*",
        r"^(?:tocar|ouvir|procurar)\s+(?:a\s+|o\s+)?(?:musica|faixa)?\s*",
    ]
    for p in prefixes:
        s = re.sub(p, "", s, flags=re.IGNORECASE).strip()

    suffixes = [
        r"\s+(?:and\s+)?(?:start\s+playing|start\s+play|play|directly\s+play)\s+(?:it\s+)?(?:on\s+youtube\s+music|on\s+yt\s+music|on\s+youtube)?$",
        r"\s+(?:on|in|no|na)\s+(?:youtube\s+music|music\.youtube|yt\s+music|youtube|yt)$",
        r"\s+on\s+ytm$",
    ]
    for sfx in suffixes:
        s = re.sub(sfx, "", s, flags=re.IGNORECASE).strip()

    s = s.strip(" :\"'.,!?")

    # If all that remains is common filler words or empty
    if not s or s.lower() in ("and", "it", "on", "song", "track", "music", "youtube", "youtube music", "on youtube music", "the song", "a song"):
        return "Still Alive Portal"

    return s


def resolve_youtube_video(query: str, timeout: float = 4.0) -> tuple[str | None, str | None]:
    """
    Resolves a search query to the top matching YouTube video ID and title.
    Returns (video_id, video_title) or (None, None) if resolution fails.
    """
    q_str = str(query).strip()
    if not q_str:
        return None, None

    # Check if direct video ID or YouTube URL was provided
    id_match = re.search(r'(?:v=|\/|youtu\.be\/)([a-zA-Z0-9_-]{11})', q_str)
    if id_match:
        return id_match.group(1), None

    try:
        encoded_query = urllib.parse.quote_plus(q_str)
        url = f"https://www.youtube.com/results?search_query={encoded_query}"
        req = urllib.request.Request(
            url,
            headers={
                "User-Agent": (
                    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                    "AppleWebKit/537.36 (KHTML, like Gecko) "
                    "Chrome/124.0.0.0 Safari/537.36"
                ),
                "Accept-Language": "en-US,en;q=0.9",
            },
        )
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            html = resp.read().decode("utf-8", errors="ignore")

        # 1. Match watch?v= links
        matches = re.findall(r'/watch\?v=([a-zA-Z0-9_-]{11})', html)
        if not matches:
            # 2. Match JSON videoId
            matches = re.findall(r'"videoId":"([a-zA-Z0-9_-]{11})"', html)

        if not matches:
            return None, None

        first_id = matches[0]

        # Extract title corresponding to the first video ID
        title = None
        title_match = re.search(
            r'"videoId":"' + re.escape(first_id) + r'"[\s\S]*?"title":\{"runs":\[\{"text":"(.*?)"\}',
            html,
        )
        if title_match:
            title = title_match.group(1).replace(r"\"", '"')

        return first_id, title
    except Exception as e:
        logger.debug("Failed to resolve YouTube video for '%s': %s", q_str, e)
        return None, None


def play_youtube(query: str, music: bool = False, open_browser: bool = True, **kwargs) -> Tuple[bool, str]:
    """
    Directly opens the song or video and starts playback on YouTube Music or YouTube.
    If music=True or query contains 'youtube music', resolves and plays on music.youtube.com.
    """
    try:
        if not query or not str(query).strip():
            return False, "Query cannot be empty."

        query_clean = str(query).strip()

        # Check if YouTube Music was requested
        is_music = bool(music) or ("youtube music" in query_clean.lower()) or ("music.youtube" in query_clean.lower())

        clean_text = clean_youtube_query(query_clean)

        # Attempt to resolve the direct video ID for instant playback
        video_id, title = resolve_youtube_video(clean_text)
        display_name = title or clean_text

        if is_music:
            if video_id:
                url = f"https://music.youtube.com/watch?v={video_id}"
                msg = f"Directly playing '{display_name}' on YouTube Music."
            else:
                encoded_query = urllib.parse.quote_plus(clean_text)
                url = f"https://music.youtube.com/search?q={encoded_query}"
                msg = f"Opened YouTube Music search for '{clean_text}'."
        else:
            if video_id:
                url = f"https://www.youtube.com/watch?v={video_id}"
                msg = f"Directly playing '{display_name}' on YouTube."
            else:
                encoded_query = urllib.parse.quote_plus(clean_text)
                url = f"https://www.youtube.com/results?search_query={encoded_query}"
                msg = f"Opened YouTube search for '{clean_text}'."

        if open_browser:
            webbrowser.open(url)

        return True, msg
    except Exception as e:
        logger.exception("Error launching YouTube playback")
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
    description="Resolves and directly plays a song or video on YouTube Music (if music=True) or YouTube.",
    sensitive=False,
)(play_youtube)

register_tool(
    name="media_control",
    description='Controls media playback. Accepted actions: "play_pause", "next_track", "prev_track".',
    sensitive=False,
)(media_control)

