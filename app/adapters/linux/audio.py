"""Linux PipeWire and PulseAudio adapter implementing AudioPort via wpctl or pactl."""

from __future__ import annotations

import logging
import re
import shutil
import subprocess

from app.ports.audio import AudioPort

logger = logging.getLogger("glados.adapters.linux.audio")


class LinuxAudioAdapter(AudioPort):
    """Controls system audio on Linux via WirePlumber (wpctl) or PulseAudio (pactl)."""

    def __init__(self) -> None:
        self._has_wpctl = shutil.which("wpctl") is not None
        self._has_pactl = shutil.which("pactl") is not None
        self._saved_volume: float | None = None
        self._is_ducked = False

    def duck_audio(self, target_volume: float = 0.2) -> bool:
        """Attenuates master volume during speech synthesis or alerts."""
        if self._is_ducked:
            return True

        current = self.get_master_volume()
        self._saved_volume = current
        target = max(0.0, min(1.0, current * target_volume))
        res = self.set_master_volume(target)
        if res:
            self._is_ducked = True
        return res

    def restore_audio(self) -> bool:
        """Restores volume level saved before ducking."""
        if not self._is_ducked:
            return True

        if self._saved_volume is not None:
            res = self.set_master_volume(self._saved_volume)
            self._saved_volume = None
            self._is_ducked = False
            return res

        self._is_ducked = False
        return True

    def get_master_volume(self) -> float:
        """Retrieves master volume as float between 0.0 and 1.0."""
        if self._has_wpctl:
            try:
                out = subprocess.check_output(
                    ["wpctl", "get-volume", "@DEFAULT_AUDIO_SINK@"],
                    text=True,
                    timeout=2.0,
                )
                match = re.search(r"Volume:\s+([0-9.]+)", out)
                if match:
                    return float(match.group(1))
            except Exception as exc:
                logger.debug("wpctl get-volume failed: %s", exc)

        if self._has_pactl:
            try:
                out = subprocess.check_output(
                    ["pactl", "get-sink-volume", "@DEFAULT_SINK@"],
                    text=True,
                    timeout=2.0,
                )
                match = re.search(r"/\s*(\d+)%\s*/", out)
                if match:
                    return int(match.group(1)) / 100.0
            except Exception as exc:
                logger.debug("pactl get-sink-volume failed: %s", exc)

        return 0.5

    def set_master_volume(self, volume: float) -> bool:
        """Sets master audio volume (0.0 to 1.0)."""
        bounded = max(0.0, min(1.0, volume))
        if self._has_wpctl:
            try:
                subprocess.run(
                    ["wpctl", "set-volume", "@DEFAULT_AUDIO_SINK@", f"{bounded:.2f}"],
                    check=True,
                    timeout=2.0,
                )
                return True
            except Exception as exc:
                logger.debug("wpctl set-volume failed: %s", exc)

        if self._has_pactl:
            try:
                percent = int(bounded * 100)
                subprocess.run(
                    ["pactl", "set-sink-volume", "@DEFAULT_SINK@", f"{percent}%"],
                    check=True,
                    timeout=2.0,
                )
                return True
            except Exception as exc:
                logger.debug("pactl set-sink-volume failed: %s", exc)

        return False

    def set_mute(self, mute: bool) -> bool:
        """Sets master audio mute state."""
        flag = "1" if mute else "0"
        if self._has_wpctl:
            try:
                subprocess.run(
                    ["wpctl", "set-mute", "@DEFAULT_AUDIO_SINK@", flag],
                    check=True,
                    timeout=2.0,
                )
                return True
            except Exception as exc:
                logger.debug("wpctl set-mute failed: %s", exc)

        if self._has_pactl:
            try:
                mute_str = "1" if mute else "0"
                subprocess.run(
                    ["pactl", "set-sink-mute", "@DEFAULT_SINK@", mute_str],
                    check=True,
                    timeout=2.0,
                )
                return True
            except Exception as exc:
                logger.debug("pactl set-sink-mute failed: %s", exc)

        return False
