"""Mock game replay clipper implementing ClipperPort."""

from __future__ import annotations

import logging

from app.ports.clipper import ClipperPort

logger = logging.getLogger("glados.adapters.mock.clipper")


class MockClipperAdapter(ClipperPort):
    """Mock clipper adapter for testing and headless execution."""

    def __init__(self, is_running: bool = False) -> None:
        self._is_running = is_running

    def is_obs_running(self) -> bool:
        """Returns mock status of recording application."""
        return self._is_running

    def launch_obs(self) -> tuple[bool, str]:
        """Simulates launching OBS Studio."""
        self._is_running = True
        return True, "Mock OBS Studio started successfully."

    def save_replay_clip(self) -> tuple[bool, str]:
        """Simulates capturing a replay buffer clip."""
        return True, "Mock highlight clip captured and archived."

    def is_recording(self) -> bool:
        """Returns True if simulated recording is active."""
        return self._is_running
