"""Protocol 4 Component: Smart Audio Ducking for GLaDOS.
Gracefully attenuates background applications (Spotify, Chrome, games, Discord)
whenever GLaDOS is speaking or listening, and smoothly restores volume afterward.
"""

import contextlib
import logging
import threading
import time
from typing import Any

from pycaw.pycaw import AudioUtilities, ISimpleAudioVolume
from tools import register_tool

logger = logging.getLogger("local_os_agent.tools.audio_ducking")

_ducking_lock = threading.Lock()
_saved_session_volumes: dict[str, float] = {}
_is_ducked = False
_ducking_enabled = True


def is_ducking_enabled() -> bool:
    return _ducking_enabled


def duck_background_audio(target_fraction: float = 0.20, exclude_names: tuple[str, ...] = ("python.exe", "pythonw.exe")):
    """
    Temporarily attenuates background audio sessions to `target_fraction` (e.g. 20% of current),
    saving previous levels for restoration.
    """
    global _is_ducked, _saved_session_volumes
    if not _ducking_enabled or _is_ducked:
        return

    with _ducking_lock:
        try:
            sessions = AudioUtilities.GetAllSessions()
            for s in sessions:
                proc = s.Process
                if not proc:
                    continue
                name = proc.name().lower()
                if any(ex in name for ex in exclude_names):
                    continue

                vol_ctl = s._ctl.QueryInterface(ISimpleAudioVolume)
                current_vol = vol_ctl.GetMasterVolume()
                if current_vol > 0.05:
                    _saved_session_volumes[name] = current_vol
                    vol_ctl.SetMasterVolume(max(0.05, current_vol * target_fraction), None)

            _is_ducked = True
        except Exception as e:
            logger.debug(f"Audio ducking exception: {e}")


def restore_background_audio():
    """Restores all ducked audio sessions to their saved volume levels."""
    global _is_ducked, _saved_session_volumes
    if not _is_ducked:
        return

    with _ducking_lock:
        try:
            sessions = AudioUtilities.GetAllSessions()
            for s in sessions:
                proc = s.Process
                if not proc:
                    continue
                name = proc.name().lower()
                if name in _saved_session_volumes:
                    vol_ctl = s._ctl.QueryInterface(ISimpleAudioVolume)
                    vol_ctl.SetMasterVolume(_saved_session_volumes[name], None)

            _saved_session_volumes.clear()
            _is_ducked = False
        except Exception as e:
            logger.debug(f"Audio restore exception: {e}")


@contextlib.contextmanager
def audio_ducked(target_fraction: float = 0.20):
    """Context manager for ducking background audio during an action."""
    duck_background_audio(target_fraction=target_fraction)
    try:
        yield
    finally:
        restore_background_audio()


@register_tool
def toggle_audio_ducking(enabled: bool | None = None) -> dict[str, Any]:
    """
    Toggles automatic audio ducking on or off. When enabled, background games,
    music, and browsers are smoothly attenuated whenever GLaDOS speaks or listens.
    """
    global _ducking_enabled
    if enabled is not None:
        _ducking_enabled = bool(enabled)
    else:
        _ducking_enabled = not _ducking_enabled

    state_str = "ENABLED" if _ducking_enabled else "DISABLED"
    return {
        "success": True,
        "enabled": _ducking_enabled,
        "message": f"Aperture Smart Audio Ducking is now {state_str}."
    }

