"""Audio and master volume control toolset."""

import logging
import platform
from typing import Tuple

logger = logging.getLogger("local_os_agent.tools.audio")


def _get_windows_volume_endpoint():
    """Retrieve Windows master IAudioEndpointVolume interface via pycaw."""
    from pycaw.pycaw import AudioUtilities, IAudioEndpointVolume
    from comtypes import CLSCTX_ALL
    import ctypes

    # Initialize COM library for the thread if not already initialized
    try:
        ctypes.windll.ole32.CoInitialize(None)
    except Exception:
        pass

    device = AudioUtilities.GetSpeakers()
    if not device:
        raise RuntimeError("No audio output device found.")

    # Modern pycaw provides EndpointVolume directly on the AudioDevice wrapper
    if hasattr(device, "EndpointVolume") and device.EndpointVolume:
        return device.EndpointVolume

    # Legacy pycaw (raw IMMDevice or older wrapper)
    if hasattr(device, "Activate"):
        interface = device.Activate(IAudioEndpointVolume._iid_, CLSCTX_ALL, None)
        return interface.QueryInterface(IAudioEndpointVolume)

    if hasattr(device, "_dev") and hasattr(device._dev, "Activate"):
        interface = device._dev.Activate(IAudioEndpointVolume._iid_, CLSCTX_ALL, None)
        return interface.QueryInterface(IAudioEndpointVolume)

    raise RuntimeError("Unable to acquire IAudioEndpointVolume from audio device.")


def set_volume(level: int) -> Tuple[bool, str]:
    """
    Sets master system volume (0–100).
    Uses SetMasterVolumeLevelScalar() to directly map 0-100 linear percentage
    to a 0.0-1.0 float without logarithmic decibel math.
    """
    try:
        level = int(level)
        clamped_level = max(0, min(100, level))
        scalar_val = clamped_level / 100.0

        if platform.system() == "Windows":
            endpoint = _get_windows_volume_endpoint()
            endpoint.SetMasterVolumeLevelScalar(scalar_val, None)
            current_pct = int(round(endpoint.GetMasterVolumeLevelScalar() * 100))
            return True, f"System volume set to {current_pct}%."
        else:
            return False, f"Audio control not implemented for {platform.system()}."
    except Exception as e:
        logger.exception("Error setting volume")
        return False, f"Failed to set volume: {e}"


def mute_toggle() -> Tuple[bool, str]:
    """Toggles the system master mute state."""
    try:
        if platform.system() == "Windows":
            endpoint = _get_windows_volume_endpoint()
            current_mute = endpoint.GetMute()
            new_mute = not current_mute
            endpoint.SetMute(new_mute, None)
            state_str = "muted" if new_mute else "unmuted"
            return True, f"System audio is now {state_str}."
        else:
            return False, f"Mute toggle not implemented for {platform.system()}."
    except Exception as e:
        logger.exception("Error toggling mute")
        return False, f"Failed to toggle mute: {e}"


# Register tools
from tools import register_tool

register_tool(
    name="set_volume",
    description="Sets master system volume (0-100).",
    sensitive=False,
)(set_volume)

register_tool(
    name="mute_toggle",
    description="Toggles the system mute state.",
    sensitive=False,
)(mute_toggle)
