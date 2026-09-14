"""Linux audio playback adapter implementing AudioPlaybackPort via pw-play, paplay, or aplay."""

from __future__ import annotations

import logging
import shutil
import subprocess
from pathlib import Path

from app.ports.audio import AudioPlaybackPort

logger = logging.getLogger("glados.adapters.linux.playback")


class LinuxAudioPlaybackAdapter(AudioPlaybackPort):
    """Audio playback on Linux using native sound utilities (pw-play, paplay, aplay)."""

    def __init__(self) -> None:
        self._current_proc: subprocess.Popen[bytes] | None = None
        self._player_bin = (
            shutil.which("pw-play")
            or shutil.which("paplay")
            or shutil.which("aplay")
            or shutil.which("ffplay")
        )

    def play_sound(self, file_path: str, block: bool = False) -> bool:
        """Plays audio file using available Linux sound player."""
        path = Path(file_path).resolve()
        if not path.exists():
            logger.warning("Playback file does not exist: %s", path)
            return False

        if not self._player_bin:
            logger.debug("No Linux sound player utility found on PATH.")
            return False

        self.stop_sound()

        try:
            cmd = [self._player_bin, str(path)]
            if "ffplay" in self._player_bin:
                cmd.extend(["-nodisp", "-autoexit"])

            if block:
                subprocess.run(cmd, check=True)
            else:
                self._current_proc = subprocess.Popen(
                    cmd, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL
                )
            return True
        except Exception as exc:
            logger.error("Linux audio playback error: %s", exc)
            return False

    def stop_sound(self) -> bool:
        """Terminates active playback process."""
        if self._current_proc and self._current_proc.poll() is None:
            try:
                self._current_proc.terminate()
                self._current_proc.wait(timeout=1.0)
            except Exception:
                try:
                    self._current_proc.kill()
                except Exception:
                    pass
            finally:
                self._current_proc = None
            return True
        self._current_proc = None
        return True

    def is_playing(self) -> bool:
        """Returns True if the playback subprocess is actively running."""
        return self._current_proc is not None and self._current_proc.poll() is None
