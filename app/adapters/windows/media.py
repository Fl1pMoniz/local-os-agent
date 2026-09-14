"""Windows media keys adapter implementing MediaKeysPort via user32 virtual key events."""

from __future__ import annotations

import logging

from app.ports.media import MediaKeysPort

logger = logging.getLogger("glados.adapters.windows.media")

VK_MEDIA_NEXT_TRACK = 0xB0
VK_MEDIA_PREV_TRACK = 0xB1
VK_MEDIA_STOP = 0xB2
VK_MEDIA_PLAY_PAUSE = 0xB3
VK_VOLUME_MUTE = 0xAD
VK_VOLUME_DOWN = 0xAE
VK_VOLUME_UP = 0xAF
KEYEVENTF_KEYUP = 0x0002


class WindowsMediaKeysAdapter(MediaKeysPort):
    """Dispatches virtual media keyboard events to Windows user32."""

    def _send_vk(self, vk_code: int) -> bool:
        """Sends keydown and keyup events for specified virtual key."""
        try:
            import ctypes

            ctypes.windll.user32.keybd_event(vk_code, 0, 0, 0)
            ctypes.windll.user32.keybd_event(vk_code, 0, KEYEVENTF_KEYUP, 0)
            return True
        except Exception as exc:
            logger.debug("Failed to dispatch VK 0x%02X: %s", vk_code, exc)
            return False

    def play_pause(self) -> bool:
        """Toggles global media play/pause state."""
        return self._send_vk(VK_MEDIA_PLAY_PAUSE)

    def next_track(self) -> bool:
        """Skips to the next media track."""
        return self._send_vk(VK_MEDIA_NEXT_TRACK)

    def previous_track(self) -> bool:
        """Navigates to previous media track."""
        return self._send_vk(VK_MEDIA_PREV_TRACK)

    def volume_up(self) -> bool:
        """Increments system audio volume."""
        return self._send_vk(VK_VOLUME_UP)

    def volume_down(self) -> bool:
        """Decrements system audio volume."""
        return self._send_vk(VK_VOLUME_DOWN)

    def mute_toggle(self) -> bool:
        """Toggles audio mute."""
        return self._send_vk(VK_VOLUME_MUTE)
