"""Portal songs toolset: GLaDOS singing 'Still Alive' and 'Want You Gone'."""

import ctypes
import logging
import threading
import time
import urllib.request
from pathlib import Path

from config import config
from tools import register_tool

logger = logging.getLogger("local_os_agent.tools.songs")

# Song storage directory
SONGS_DIR = config.audio_cache_dir / "songs"
SONGS_DIR.mkdir(parents=True, exist_ok=True)

STILL_ALIVE_URL = "https://i1.theportalwiki.net/img/7/7a/Portal_still_alive.mp3"
WANT_YOU_GONE_URL = "https://i1.theportalwiki.net/img/5/5b/Portal2-13-Want_You_Gone.mp3"

MCI_ALIAS = "glados_song_player"
_lock = threading.Lock()
_current_song: str | None = None
_playback_thread: threading.Thread | None = None
_stop_event = threading.Event()


def _extract_from_steam_vpk() -> bool:
    """Attempts to extract portal_still_alive.mp3 from local Steam Portal install."""
    target_path = SONGS_DIR / "still_alive.mp3"
    if target_path.exists() and target_path.stat().st_size > 100000:
        return True

    try:
        from tools.steam import _find_steam_root

        steam_root = _find_steam_root()
        if not steam_root:
            return False

        candidate_vpk = (
            steam_root / "steamapps" / "common" / "Portal" / "portal" / "portal_pak_dir.vpk"
        )
        if candidate_vpk.exists():
            import vpk

            pak = vpk.open(str(candidate_vpk))
            entry = pak.get_file("sound/music/portal_still_alive.mp3")
            if entry:
                with open(target_path, "wb") as f:
                    f.write(entry.read())
                logger.info(
                    f"Extracted still_alive.mp3 from Steam Portal VPK ({target_path.stat().st_size} bytes)"
                )
                return True
    except Exception as e:
        logger.debug(f"Steam Portal VPK extraction failed: {e}")
    return False


def get_song_file(song_key: str) -> Path | None:
    """Resolves and ensures the specified song MP3 exists locally."""
    normalized = song_key.lower().strip().replace(" ", "_").replace("-", "_")

    if "still" in normalized or "alive" in normalized:
        file_path = SONGS_DIR / "still_alive.mp3"
        if not file_path.exists() or file_path.stat().st_size < 100000:
            if not _extract_from_steam_vpk():
                try:
                    logger.info("Downloading Still Alive from Portal Wiki...")
                    req = urllib.request.Request(
                        STILL_ALIVE_URL, headers={"User-Agent": "Mozilla/5.0"}
                    )
                    with urllib.request.urlopen(req) as resp, open(file_path, "wb") as f:
                        f.write(resp.read())
                    logger.info("Downloaded still_alive.mp3 successfully.")
                except Exception as e:
                    logger.error(f"Failed to download still_alive.mp3: {e}")
                    return None
        return file_path

    elif "want" in normalized or "gone" in normalized:
        file_path = SONGS_DIR / "want_you_gone.mp3"
        if not file_path.exists() or file_path.stat().st_size < 100000:
            try:
                logger.info("Downloading Want You Gone from Portal Wiki...")
                req = urllib.request.Request(
                    WANT_YOU_GONE_URL, headers={"User-Agent": "Mozilla/5.0"}
                )
                with urllib.request.urlopen(req) as resp, open(file_path, "wb") as f:
                    f.write(resp.read())
                logger.info("Downloaded want_you_gone.mp3 successfully.")
            except Exception as e:
                logger.error(f"Failed to download want_you_gone.mp3: {e}")
                return None
        return file_path

    return None


def is_song_playing() -> bool:
    """Checks if a song is currently playing."""
    with _lock:
        return _current_song is not None


@register_tool("stop_song", description="Stops any currently playing GLaDOS song.")
def stop_song() -> tuple[bool, str]:
    """Stops the currently playing song via Windows MCI."""
    global _current_song, _playback_thread
    with _lock:
        if _current_song is None:
            return True, "No song is currently playing."

        song_name = _current_song
        _stop_event.set()
        try:
            winmm = ctypes.windll.winmm
            winmm.mciSendStringW(f"stop {MCI_ALIAS}", None, 0, 0)
            winmm.mciSendStringW(f"close {MCI_ALIAS}", None, 0, 0)
        except Exception as e:
            logger.warning(f"Error closing MCI device: {e}")

        _current_song = None
        return True, f"Stopped playback of '{song_name}'."


def _play_song_worker(file_path: Path, song_name: str) -> None:
    """Worker thread that opens and plays the song via MCI until completion or stop."""
    global _current_song
    try:
        from voice.tts import tts_engine

        tts_engine.stop()
    except Exception:
        pass

    try:
        from voice.audio_arbiter import GLOBAL_AUDIO_LOCK

        with GLOBAL_AUDIO_LOCK:
            winmm = ctypes.windll.winmm
            abs_path = str(file_path.resolve())

            try:
                # Give GLaDOS's spoken intro line time to complete before musical intro begins
                time.sleep(0.3)
                if _stop_event.is_set():
                    return

                # Close any lingering alias first
                winmm.mciSendStringW(f"close {MCI_ALIAS}", None, 0, 0)

                open_cmd = f'open "{abs_path}" type mpegvideo alias {MCI_ALIAS}'
                err = winmm.mciSendStringW(open_cmd, None, 0, 0)
                if err != 0:
                    if not _stop_event.is_set():
                        logger.debug(f"MCI open returned code {err}")
                    with _lock:
                        _current_song = None
                    return

                play_cmd = f"play {MCI_ALIAS}"
                winmm.mciSendStringW(play_cmd, None, 0, 0)

                # Monitor playback until finished or stopped
                status_buffer = ctypes.create_unicode_buffer(128)
                while not _stop_event.is_set():
                    time.sleep(0.5)
                    err = winmm.mciSendStringW(f"status {MCI_ALIAS} mode", status_buffer, 128, 0)
                    mode = status_buffer.value.lower()
                    if mode != "playing" and mode != "paused":
                        break

            except Exception as e:
                logger.exception(f"Error during song playback: {e}")
            finally:
                winmm.mciSendStringW(f"close {MCI_ALIAS}", None, 0, 0)
                with _lock:
                    if _current_song == song_name:
                        _current_song = None
                try:
                    from ui.state import ui_state

                    ui_state.update(state="idle", song="")
                except Exception:
                    pass
    except Exception as e:
        logger.debug(f"Error in song worker: {e}")


@register_tool(
    "sing_song",
    description="Plays an authentic Portal song sung by GLaDOS ('still_alive' or 'want_you_gone').",
)
def sing_song(song_name: str) -> tuple[bool, str]:
    """
    Plays an authentic Portal song sung by GLaDOS ('still_alive' or 'want_you_gone') in the background.
    """
    global _current_song, _playback_thread, _stop_event

    resolved_path = get_song_file(song_name)
    if not resolved_path or not resolved_path.exists():
        return (
            False,
            f"Could not find or retrieve song for query '{song_name}'. Supported songs: 'still_alive', 'want_you_gone'.",
        )

    display_name = "Still Alive" if "still" in resolved_path.name else "Want You Gone"

    # Stop any current song
    stop_song()

    with _lock:
        _stop_event = threading.Event()
        _current_song = display_name
        _playback_thread = threading.Thread(
            target=_play_song_worker,
            args=(resolved_path, display_name),
            daemon=True,
        )
        _playback_thread.start()

    try:
        from ui.state import ui_state

        ui_state.update(state="singing", song=display_name, text=f"Now singing: {display_name}")
    except Exception:
        pass

    logger.info(f"Initiated playback of {display_name} ({resolved_path})")
    return (
        True,
        f"Now playing '{display_name}' by GLaDOS (Aperture Science Psychoacoustics Laboratory).",
    )
