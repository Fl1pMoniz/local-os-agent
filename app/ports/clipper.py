"""Game and desktop replay recording port definitions."""

from __future__ import annotations

from typing import Protocol, runtime_checkable


@runtime_checkable
class ClipperPort(Protocol):
    """Protocol for interacting with screen capture replay buffers (e.g. OBS Studio, ShadowPlay)."""

    def is_obs_running(self) -> bool:
        """Returns True if the recording application process is active."""
        ...

    def launch_obs(self) -> tuple[bool, str]:
        """Launches the recording application if not currently running."""
        ...

    def save_replay_clip(self) -> tuple[bool, str]:
        """Triggers the replay buffer to flush the last recorded duration to disk."""
        ...

    def is_recording(self) -> bool:
        """Returns True if active recording or replay buffer is currently engaged."""
        ...
