"""Audio and master volume control toolset."""

import logging
import platform
from typing import Any, Tuple

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


def get_current_volume() -> int:
    """Returns current system master volume percentage (0-100)."""
    try:
        if platform.system() == "Windows":
            endpoint = _get_windows_volume_endpoint()
            return int(round(endpoint.GetMasterVolumeLevelScalar() * 100))
    except Exception as e:
        logger.debug(f"Error reading current volume: {e}")
    return 50


def set_volume(level: int = 50, volume: int | None = None, value: int | None = None, **kwargs) -> Tuple[bool, str]:
    """
    Sets master system volume (0–100).
    Accepts synonyms: level, volume, value.
    """
    try:
        raw_val = volume if volume is not None else (value if value is not None else level)
        target_level = int(raw_val)
        clamped_level = max(0, min(100, target_level))
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


def change_volume_relative(delta: int = 10, **kwargs) -> Tuple[bool, str]:
    """
    Increases or decreases system volume relatively by delta percent (e.g. +15, -15).
    """
    try:
        current = get_current_volume()
        new_level = max(0, min(100, current + int(delta)))
        return set_volume(level=new_level)
    except Exception as e:
        logger.exception("Error adjusting relative volume")
        return False, f"Failed to adjust volume: {e}"


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


def set_app_volume(app_name: str, level: int) -> Tuple[bool, str]:
    """
    Sets the volume of a specific running application (0–100) using pycaw ISimpleAudioVolume.
    Matches the application name against active audio sessions.
    """
    try:
        if not app_name or not app_name.strip():
            return False, "Application name cannot be empty."

        level = max(0, min(100, int(level)))
        scalar_val = level / 100.0
        app_query = app_name.strip().lower().replace(".exe", "")

        if platform.system() == "Windows":
            from pycaw.pycaw import AudioUtilities
            import ctypes

            try:
                ctypes.windll.ole32.CoInitialize(None)
            except Exception:
                pass

            sessions = AudioUtilities.GetAllSessions()
            matched_sessions = []
            available_apps = set()

            for session in sessions:
                if session.Process:
                    p_name = session.Process.name()
                    if p_name:
                        base_name = p_name.lower().replace(".exe", "")
                        available_apps.add(base_name)
                        if app_query in base_name or app_query in p_name.lower():
                            matched_sessions.append((p_name, session.SimpleAudioVolume))

            if not matched_sessions:
                apps_list = ", ".join(sorted(list(available_apps))[:6]) if available_apps else "None"
                return False, f"No active audio session found for '{app_name}'. (Active audio apps: {apps_list})"

            for proc_name, simple_volume in matched_sessions:
                simple_volume.SetMasterVolume(scalar_val, None)

            names = list(set(p for p, _ in matched_sessions))
            return True, f"Set volume for {', '.join(names)} to {level}%."
        else:
            return False, f"Per-app audio control not implemented for {platform.system()}."
    except Exception as e:
        logger.exception(f"Error setting app volume for '{app_name}'")
        return False, f"Failed to set app volume for '{app_name}': {e}"


def list_app_volumes() -> Tuple[bool, dict[str, Any]]:
    """
    Returns a dictionary of currently active audio applications and their volume levels (0-100).
    """
    try:
        if platform.system() == "Windows":
            from pycaw.pycaw import AudioUtilities
            import ctypes

            try:
                ctypes.windll.ole32.CoInitialize(None)
            except Exception:
                pass

            sessions = AudioUtilities.GetAllSessions()
            app_data = {}

            for session in sessions:
                if session.Process:
                    p_name = session.Process.name()
                    if p_name:
                        vol = session.SimpleAudioVolume
                        pct = int(round(vol.GetMasterVolume() * 100))
                        muted = bool(vol.GetMute())
                        app_data[p_name] = {"volume": pct, "muted": muted, "pid": session.Process.pid}

            return True, app_data
        else:
            return False, {"error": f"Not implemented for {platform.system()}."}
    except Exception as e:
        logger.exception("Error listing app volumes")
        return False, {"error": str(e)}


# Register tools
from tools import register_tool

register_tool(
    name="set_volume",
    description="Sets master system volume (0-100).",
    sensitive=False,
)(set_volume)

register_tool(
    name="change_volume_relative",
    description="Adjusts system volume up or down by a relative percentage (e.g. +15 or -15).",
    sensitive=False,
)(change_volume_relative)

register_tool(
    name="mute_toggle",
    description="Toggles the system mute state.",
    sensitive=False,
)(mute_toggle)

register_tool(
    name="set_app_volume",
    description="Sets the volume for a specific application (0-100), e.g. Spotify, Discord, Chrome.",
    sensitive=False,
)(set_app_volume)

register_tool(
    name="list_app_volumes",
    description="Lists active audio applications with their current volume levels and mute states.",
    sensitive=False,
)(list_app_volumes)

