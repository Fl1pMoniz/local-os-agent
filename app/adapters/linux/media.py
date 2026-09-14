"""Linux media control adapter implementing MediaKeysPort via playerctl and MPRIS."""

from __future__ import annotations

import logging
import shutil
import subprocess

from app.ports.media import MediaKeysPort

logger = logging.getLogger("glados.adapters.linux.media")


class LinuxMediaKeysAdapter(MediaKeysPort):
    """Dispatches media transport commands on Linux using playerctl or DBus."""

    def __init__(self) -> None:
        self._has_playerctl = shutil.which("playerctl") is not None

    def _run_playerctl(self, command: str) -> bool:
        """Executes a playerctl media action."""
        if not self._has_playerctl:
            logger.debug("playerctl is not installed on this system.")
            return False

        try:
            subprocess.run(["playerctl", command], check=True, timeout=2.0)
            return True
        except Exception as exc:
            logger.debug("playerctl %s failed: %s", command, exc)
            return False

    def play_pause(self) -> bool:
        """Toggles media play/pause state across active MPRIS players."""
        return self._run_playerctl("play-pause")

    def next_track(self) -> bool:
        """Advances to the next track."""
        return self._run_playerctl("next")

    def previous_track(self) -> bool:
        """Returns to the previous track."""
        return self._run_playerctl("previous")

    def volume_up(self) -> bool:
        """Increments player volume by 5%."""
        return self._run_playerctl("volume 0.05+")

    def volume_down(self) -> bool:
        """Decrements player volume by 5%."""
        return self._run_playerctl("volume 0.05-")

    def mute_toggle(self) -> bool:
        """Toggles audio mute via wpctl or pactl."""
        if shutil.which("wpctl"):
            try:
                subprocess.run(
                    ["wpctl", "set-mute", "@DEFAULT_AUDIO_SINK@", "toggle"],
                    check=True,
                    timeout=2.0,
                )
                return True
            except Exception:
                pass

        if shutil.which("pactl"):
            try:
                subprocess.run(
                    ["pactl", "set-sink-mute", "@DEFAULT_SINK@", "toggle"],
                    check=True,
                    timeout=2.0,
                )
                return True
            except Exception:
                pass

        return False
