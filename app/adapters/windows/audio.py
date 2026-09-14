"""Windows CoreAudio adapter implementing AudioPort via pycaw and COM."""

from __future__ import annotations

import logging
from typing import Any

from app.ports.audio import AudioPort

logger = logging.getLogger("glados.adapters.windows.audio")


class WindowsAudioAdapter(AudioPort):
    """Controls Windows system audio and application ducking using pycaw."""

    def __init__(self) -> None:
        self._saved_session_volumes: dict[int, float] = {}
        self._is_ducked = False

    def _get_endpoint(self) -> Any:
        """Retrieves Windows master audio endpoint via pycaw."""
        import ctypes

        from comtypes import CLSCTX_ALL
        from pycaw.pycaw import AudioUtilities, IAudioEndpointVolume

        try:
            ctypes.windll.ole32.CoInitialize(None)
        except Exception:
            pass

        device = AudioUtilities.GetSpeakers()
        if not device:
            raise RuntimeError("No Windows audio output device found.")

        if hasattr(device, "EndpointVolume") and device.EndpointVolume:
            return device.EndpointVolume

        if hasattr(device, "Activate"):
            interface = device.Activate(IAudioEndpointVolume._iid_, CLSCTX_ALL, None)
            return interface.QueryInterface(IAudioEndpointVolume)

        if hasattr(device, "_dev") and hasattr(device._dev, "Activate"):
            interface = device._dev.Activate(IAudioEndpointVolume._iid_, CLSCTX_ALL, None)
            return interface.QueryInterface(IAudioEndpointVolume)

        raise RuntimeError("Unable to acquire IAudioEndpointVolume.")

    def duck_audio(self, target_volume: float = 0.2) -> bool:
        """Ducks non-Python background audio sessions to target volume fraction."""
        if self._is_ducked:
            return True

        try:
            from pycaw.pycaw import AudioUtilities, ISimpleAudioVolume

            sessions = AudioUtilities.GetAllSessions()
            for s in sessions:
                proc = s.Process
                if not proc:
                    continue
                name = (proc.name() or "").lower()
                if "python" in name:
                    continue

                vol_ctl = s._ctl.QueryInterface(ISimpleAudioVolume)
                current_vol = vol_ctl.GetMasterVolume()
                self._saved_session_volumes[s.ProcessId] = current_vol
                vol_ctl.SetMasterVolume(max(0.0, min(1.0, current_vol * target_volume)), None)

            self._is_ducked = True
            return True
        except Exception as exc:
            logger.debug("Failed to duck Windows audio: %s", exc)
            return False

    def restore_audio(self) -> bool:
        """Restores previously ducked audio sessions to their original volumes."""
        if not self._is_ducked:
            return True

        try:
            from pycaw.pycaw import AudioUtilities, ISimpleAudioVolume

            sessions = AudioUtilities.GetAllSessions()
            for s in sessions:
                if s.ProcessId in self._saved_session_volumes:
                    orig_vol = self._saved_session_volumes[s.ProcessId]
                    vol_ctl = s._ctl.QueryInterface(ISimpleAudioVolume)
                    vol_ctl.SetMasterVolume(orig_vol, None)

            self._saved_session_volumes.clear()
            self._is_ducked = False
            return True
        except Exception as exc:
            logger.debug("Failed to restore Windows audio: %s", exc)
            self._saved_session_volumes.clear()
            self._is_ducked = False
            return False

    def get_master_volume(self) -> float:
        """Returns master volume level between 0.0 and 1.0."""
        try:
            endpoint = self._get_endpoint()
            return float(endpoint.GetMasterVolumeLevelScalar())
        except Exception as exc:
            logger.debug("Failed to read master volume: %s", exc)
            return 0.5

    def set_master_volume(self, volume: float) -> bool:
        """Sets master volume level (0.0 to 1.0)."""
        try:
            endpoint = self._get_endpoint()
            bounded = max(0.0, min(1.0, volume))
            endpoint.SetMasterVolumeLevelScalar(bounded, None)
            return True
        except Exception as exc:
            logger.debug("Failed to set master volume: %s", exc)
            return False

    def set_mute(self, mute: bool) -> bool:
        """Sets master audio mute state."""
        try:
            endpoint = self._get_endpoint()
            endpoint.SetMute(1 if mute else 0, None)
            return True
        except Exception as exc:
            logger.debug("Failed to set mute state: %s", exc)
            return False
