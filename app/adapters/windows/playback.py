"""Windows audio playback adapter implementing AudioPlaybackPort via MCI and sounddevice."""

from __future__ import annotations

import logging
import threading
from pathlib import Path

from app.ports.audio import AudioPlaybackPort

logger = logging.getLogger("glados.adapters.windows.playback")

MCI_ALIAS = "glados_win_player"


class WindowsAudioPlaybackAdapter(AudioPlaybackPort):
    """Low-latency audio playback on Windows using MCI winmm."""

    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._is_playing = False

    def play_sound(self, file_path: str, block: bool = False) -> bool:
        """Plays audio file using Windows MCI with blocking or non-blocking mode."""
        import ctypes

        path = Path(file_path).resolve()
        if not path.exists():
            logger.warning("Audio playback file not found: %s", path)
            return False

        with self._lock:
            try:
                winmm = ctypes.windll.winmm
                # Close any previous playback session
                winmm.mciSendStringW(f"close {MCI_ALIAS}", None, 0, 0)
                open_cmd = f'open "{path}" type mpegvideo alias {MCI_ALIAS}'
                res = winmm.mciSendStringW(open_cmd, None, 0, 0)
                if res != 0:
                    # Fallback to auto type
                    winmm.mciSendStringW(f'open "{path}" alias {MCI_ALIAS}', None, 0, 0)

                wait_flag = " wait" if block else ""
                winmm.mciSendStringW(f"play {MCI_ALIAS}{wait_flag}", None, 0, 0)
                self._is_playing = True
                return True
            except Exception as exc:
                logger.error("Failed to play audio file %s via MCI: %s", path, exc)
                self._is_playing = False
                return False

    def stop_sound(self) -> bool:
        """Halts active MCI sound playback and closes device."""
        import ctypes

        with self._lock:
            try:
                winmm = ctypes.windll.winmm
                winmm.mciSendStringW(f"stop {MCI_ALIAS}", None, 0, 0)
                winmm.mciSendStringW(f"close {MCI_ALIAS}", None, 0, 0)
                self._is_playing = False
                return True
            except Exception as exc:
                logger.debug("Failed to stop MCI sound: %s", exc)
                self._is_playing = False
                return False

    def is_playing(self) -> bool:
        """Returns True if MCI player is actively engaged."""
        return self._is_playing
