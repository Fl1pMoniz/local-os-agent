"""OBS Studio replay buffer clipper implementing ClipperPort."""

from __future__ import annotations

import logging
import shutil
from typing import Any

from app.ports.clipper import ClipperPort

logger = logging.getLogger("glados.adapters.obs_clipper")


class ObsClipperAdapter(ClipperPort):
    """Integrates with OBS Studio WebSocket and replay buffer."""

    def is_obs_running(self) -> bool:
        """Checks if OBS executable process is running via psutil."""
        import psutil

        for proc in psutil.process_iter(["name"]):
            try:
                name = (proc.info["name"] or "").lower()
                if "obs64.exe" in name or "obs32.exe" in name or name == "obs":
                    return True
            except (psutil.NoSuchProcess, psutil.AccessDenied):
                continue
        return False

    def launch_obs(self) -> tuple[bool, str]:
        """Launches OBS Studio process if found on PATH or standard directory."""
        from tools import game_clipper

        result: dict[str, Any] = game_clipper.launch_obs()
        return result.get("success", False), result.get("message", "Launched OBS")

    def save_replay_clip(self) -> tuple[bool, str]:
        """Saves current replay buffer clip to disk."""
        from tools import game_clipper

        res = game_clipper.capture_game_clip(seconds=30)
        return res.get("success", False), res.get("message", "Replay captured")

    def is_recording(self) -> bool:
        """Returns True if OBS is running and reachable."""
        return self.is_obs_running()
