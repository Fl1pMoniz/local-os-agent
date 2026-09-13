"""Authentic Portal Sound Effects and Radio Music toolset."""

import ctypes
import logging
import threading
import time
from pathlib import Path
from typing import Tuple

from config import config
from tools import register_tool

logger = logging.getLogger("local_os_agent.tools.sfx")

SFX_DIR = config.audio_cache_dir / "sfx"
SFX_DIR.mkdir(parents=True, exist_ok=True)

MCI_SFX_ALIAS = "glados_sfx_player"
_lock = threading.Lock()
_current_sfx: str | None = None
_sfx_thread: threading.Thread | None = None
_stop_event = threading.Event()

VPK_SFX_MAP: dict[str, str] = {
    "radio": "sound/ambient/music/looping_radio_mix.wav",
    "portal_radio": "sound/ambient/music/looping_radio_mix.wav",
    "turret_hello": "sound/npc/turret_floor/turret_active_1.wav",
    "turret_target": "sound/npc/turret_floor/turret_active_2.wav",
    "turret_search": "sound/npc/turret_floor/turret_search_1.wav",
    "turret_lost": "sound/npc/turret_floor/turret_search_2.wav",
    "turret_retire": "sound/npc/turret_floor/turret_retire_1.wav",
    "turret_goodnight": "sound/npc/turret_floor/turret_disabled_1.wav",
}


def _extract_sfx_from_vpk(vpk_entry: str, dest_file: Path) -> bool:
    """Extracts a specific audio entry from Portal VPK."""
    try:
        from tools.steam import _find_steam_root
        steam_root = _find_steam_root()
        if not steam_root:
            return False

        vpk_p = steam_root / "steamapps" / "common" / "Portal" / "portal" / "portal_pak_dir.vpk"
        if not vpk_p.exists():
            return False

        import vpk
        pak = vpk.open(str(vpk_p))
        entry = pak.get_file(vpk_entry)
        if entry:
            with open(dest_file, "wb") as f:
                f.write(entry.read())
            return dest_file.exists() and dest_file.stat().st_size > 0
    except Exception as e:
        logger.debug(f"Failed to extract {vpk_entry} from VPK: {e}")
    return False


def get_sfx_path(effect_name: str) -> Path | None:
    """Resolves and extracts the specified SFX audio file."""
    normalized = effect_name.lower().strip().replace(" ", "_").replace("-", "_")

    # Match aliases
    matched_entry = None
    file_name = f"{normalized}.wav"

    if "radio" in normalized:
        matched_entry = VPK_SFX_MAP["radio"]
        file_name = "radio.wav"
    elif "turret" in normalized:
        if "target" in normalized or "acquire" in normalized:
            matched_entry = VPK_SFX_MAP["turret_target"]
            file_name = "turret_target.wav"
        elif "lost" in normalized or "still there" in normalized:
            matched_entry = VPK_SFX_MAP["turret_lost"]
            file_name = "turret_lost.wav"
        elif "goodnight" in normalized or "sleep" in normalized:
            matched_entry = VPK_SFX_MAP["turret_goodnight"]
            file_name = "turret_goodnight.wav"
        else:
            matched_entry = VPK_SFX_MAP["turret_hello"]
            file_name = "turret_hello.wav"
    else:
        matched_entry = VPK_SFX_MAP.get(normalized, VPK_SFX_MAP["radio"])

    dest_file = SFX_DIR / file_name
    if dest_file.exists() and dest_file.stat().st_size > 0:
        return dest_file

    if matched_entry and _extract_sfx_from_vpk(matched_entry, dest_file):
        return dest_file

    return None


@register_tool("stop_sfx", description="Stops any currently playing sound effect or radio loop.")
def stop_sfx() -> Tuple[bool, str]:
    """Stops the currently playing SFX."""
    global _current_sfx, _stop_event
    with _lock:
        if _current_sfx is None:
            return True, "No sound effect is currently playing."

        name = _current_sfx
        _stop_event.set()
        try:
            winmm = ctypes.windll.winmm
            winmm.mciSendStringW(f"stop {MCI_SFX_ALIAS}", None, 0, 0)
            winmm.mciSendStringW(f"close {MCI_SFX_ALIAS}", None, 0, 0)
        except Exception:
            pass

        _current_sfx = None
        try:
            from ui.state import ui_state
            ui_state.update(state="idle")
        except Exception:
            pass
        return True, f"Stopped playback of '{name}'."


def _play_sfx_worker(file_path: Path, name: str) -> None:
    global _current_sfx
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
                time.sleep(0.1)
                if _stop_event.is_set():
                    return

                winmm.mciSendStringW(f"close {MCI_SFX_ALIAS}", None, 0, 0)
                open_cmd = f'open "{abs_path}" type waveaudio alias {MCI_SFX_ALIAS}'
                err = winmm.mciSendStringW(open_cmd, None, 0, 0)
                if err != 0:
                    with _lock:
                        _current_sfx = None
                    return

                play_cmd = f"play {MCI_SFX_ALIAS}"
                winmm.mciSendStringW(play_cmd, None, 0, 0)

                status_buffer = ctypes.create_unicode_buffer(128)
                while not _stop_event.is_set():
                    time.sleep(0.3)
                    winmm.mciSendStringW(f"status {MCI_SFX_ALIAS} mode", status_buffer, 128, 0)
                    if status_buffer.value.lower() not in ("playing", "paused"):
                        break
            except Exception as e:
                logger.debug(f"SFX error: {e}")
            finally:
                winmm.mciSendStringW(f"close {MCI_SFX_ALIAS}", None, 0, 0)
                with _lock:
                    if _current_sfx == name:
                        _current_sfx = None
                try:
                    from ui.state import ui_state
                    ui_state.update(state="idle")
                except Exception:
                    pass
    except Exception as e:
        logger.debug(f"Error in sfx worker: {e}")


@register_tool("play_portal_sfx", description="Plays authentic Portal sound effects: 'radio' (Brazilian samba loop), 'turret_hello', 'turret_target', 'turret_lost', or 'turret_goodnight'.")
def play_portal_sfx(effect_name: str = "radio") -> Tuple[bool, str]:
    """Plays an authentic Portal sound effect in the background."""
    global _current_sfx, _sfx_thread, _stop_event

    sfx_file = get_sfx_path(effect_name)
    if not sfx_file or not sfx_file.exists():
        return False, f"Could not find or extract sound effect for '{effect_name}'."

    display_name = sfx_file.stem.replace("_", " ").title()

    stop_sfx()

    with _lock:
        _stop_event = threading.Event()
        _current_sfx = display_name
        _sfx_thread = threading.Thread(
            target=_play_sfx_worker,
            args=(sfx_file, display_name),
            daemon=True,
        )
        _sfx_thread.start()

    try:
        from ui.state import ui_state
        ui_state.update(state="singing" if "radio" in effect_name.lower() else "speaking", text=f"Portal SFX: {display_name}")
    except Exception:
        pass

    return True, f"Playing Portal sound effect: '{display_name}'."

