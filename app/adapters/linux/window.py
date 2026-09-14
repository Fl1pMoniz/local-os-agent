"""Linux window inspection adapter implementing WindowInspectionPort."""

from __future__ import annotations

import json
import logging
import shutil
import subprocess

from app.ports.system import WindowInspectionPort

logger = logging.getLogger("glados.adapters.linux.window")


class LinuxWindowInspectAdapter(WindowInspectionPort):
    """Inspects active focused window title on Linux (X11 and Wayland)."""

    def get_active_window_title(self) -> str:
        """Determines focused window title across desktop environments."""
        # 1. Hyprland compositor
        if shutil.which("hyprctl"):
            try:
                out = subprocess.check_output(
                    ["hyprctl", "activewindow", "-j"], text=True, timeout=1.0
                )
                data = json.loads(out)
                title = data.get("title", "")
                if title:
                    return str(title)
            except Exception:
                pass

        # 2. X11 via xdotool
        if shutil.which("xdotool"):
            try:
                win_id = subprocess.check_output(
                    ["xdotool", "getactivewindow"], text=True, timeout=1.0
                ).strip()
                title = subprocess.check_output(
                    ["xdotool", "getwindowname", win_id], text=True, timeout=1.0
                ).strip()
                if title:
                    return title
            except Exception:
                pass

        # 3. Sway compositor
        if shutil.which("swaymsg"):
            try:
                out = subprocess.check_output(["swaymsg", "-t", "get_tree"], text=True, timeout=1.0)
                tree = json.loads(out)

                def _find_focused(node: dict) -> str | None:
                    if node.get("focused"):
                        return node.get("name")
                    for child in node.get("nodes", []) + node.get("floating_nodes", []):
                        found = _find_focused(child)
                        if found:
                            return found
                    return None

                focused = _find_focused(tree)
                if focused:
                    return focused
            except Exception:
                pass

        return "Desktop"
