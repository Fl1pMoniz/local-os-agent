"""Media playback and streaming server port definitions."""

from __future__ import annotations

from typing import Any, Protocol, runtime_checkable


@runtime_checkable
class MediaKeysPort(Protocol):
    """Protocol for hardware and operating system media transport keys."""

    def play_pause(self) -> bool:
        """Toggles play and pause on the active system media player."""
        ...

    def next_track(self) -> bool:
        """Skips to the next media track."""
        ...

    def previous_track(self) -> bool:
        """Returns to the previous media track or restarts the current track."""
        ...

    def volume_up(self) -> bool:
        """Increments system media volume."""
        ...

    def volume_down(self) -> bool:
        """Decrements system media volume."""
        ...

    def mute_toggle(self) -> bool:
        """Toggles audio mute state."""
        ...


@runtime_checkable
class StreamingPort(Protocol):
    """Protocol for interacting with remote media streaming servers (e.g. Jellyfin, Plex)."""

    def search_and_play(self, query: str) -> tuple[bool, str]:
        """Searches the streaming library and commands playback on the active client."""
        ...

    def get_now_playing(self) -> tuple[bool, dict[str, Any]]:
        """Retrieves real-time session telemetry of the currently playing track/video."""
        ...
