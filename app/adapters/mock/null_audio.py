"""Headless and mock audio adapter implementing AudioPort and AudioPlaybackPort."""

from __future__ import annotations

import logging

from app.ports.audio import AudioPlaybackPort, AudioPort

logger = logging.getLogger("glados.adapters.mock.audio")


class NullAudioAdapter(AudioPort, AudioPlaybackPort):
    """No-op audio adapter for headless servers, Docker containers, and test suites."""

    def __init__(self) -> None:
        self._volume = 0.5
        self._muted = False
        self._is_playing = False

    def duck_audio(self, target_volume: float = 0.2) -> bool:
        """Simulates audio ducking without manipulating hardware."""
        logger.debug("NullAudioAdapter: duck_audio called (target=%s)", target_volume)
        return True

    def restore_audio(self) -> bool:
        """Simulates audio restoration."""
        logger.debug("NullAudioAdapter: restore_audio called")
        return True

    def get_master_volume(self) -> float:
        """Returns mock volume level."""
        return self._volume

    def set_master_volume(self, volume: float) -> bool:
        """Sets mock volume level."""
        self._volume = max(0.0, min(1.0, volume))
        return True

    def set_mute(self, mute: bool) -> bool:
        """Sets mock mute state."""
        self._muted = mute
        return True

    def play_sound(self, file_path: str, block: bool = False) -> bool:
        """Simulates audio file playback without emitting sound."""
        logger.debug("NullAudioAdapter: play_sound called for %s", file_path)
        return True

    def stop_sound(self) -> bool:
        """Simulates stopping audio playback."""
        logger.debug("NullAudioAdapter: stop_sound called")
        self._is_playing = False
        return True

    def is_playing(self) -> bool:
        """Returns simulated playback state."""
        return self._is_playing
