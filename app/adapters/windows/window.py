"""Windows window inspection adapter implementing WindowInspectionPort."""

from __future__ import annotations

import logging

from app.ports.system import WindowInspectionPort

logger = logging.getLogger("glados.adapters.windows.window")


class WindowsWindowInspectAdapter(WindowInspectionPort):
    """Inspects focused window title using Windows user32 Win32 API."""

    def get_active_window_title(self) -> str:
        """Returns the title text of the current foreground window."""
        try:
            import ctypes

            user32 = ctypes.windll.user32
            hwnd = user32.GetForegroundWindow()
            if not hwnd:
                return "Desktop"

            length = user32.GetWindowTextLengthW(hwnd)
            if length == 0:
                return "Unknown Application"

            buff = ctypes.create_unicode_buffer(length + 1)
            user32.GetWindowTextW(hwnd, buff, length + 1)
            title = buff.value.strip()
            return title if title else "Desktop"
        except Exception as exc:
            logger.debug("Failed to get active window title on Windows: %s", exc)
            return "Unknown Application"
