"""Audio device and volume management port definitions."""

from __future__ import annotations

from typing import Protocol, runtime_checkable


@runtime_checkable
class AudioPort(Protocol):
    """Protocol for system audio manipulation, including master volume and application ducking."""

    def duck_audio(self, target_volume: float = 0.2) -> bool:
        """Ducks background application audio during speech synthesis or alerts."""
        ...

    def restore_audio(self) -> bool:
        """Restores previously ducked background application audio to original levels."""
        ...

    def get_master_volume(self) -> float:
        """Returns the current master output volume level as a percentage between 0.0 and 1.0."""
        ...

    def set_master_volume(self, volume: float) -> bool:
        """Sets the system master output volume (0.0 to 1.0)."""
        ...

    def set_mute(self, mute: bool) -> bool:
        """Sets the system mute state."""
        ...


@runtime_checkable
class AudioPlaybackPort(Protocol):
    """Protocol for low-latency sound effects and speech audio playback."""

    def play_sound(self, file_path: str, block: bool = False) -> bool:
        """Plays an audio file on the primary output device."""
        ...

    def stop_sound(self) -> bool:
        """Immediately halts any currently playing sound effect or audio track."""
        ...

    def is_playing(self) -> bool:
        """Returns True if audio playback is currently in progress."""
        ...
