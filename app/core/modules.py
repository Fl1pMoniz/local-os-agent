"""Dependency injection module bindings based on runtime platform and configuration.

Selects concrete operating system adapters for Windows, Linux, Darwin, or headless
environments using Injector.
"""

from __future__ import annotations

import logging
import sys

from injector import Binder, Module, singleton

from app.adapters.common.file_lock import FileInstanceLock
from app.adapters.common.flight_radar import FlightRadarAdapter
from app.adapters.common.gemini_vision import GeminiVisionAdapter
from app.adapters.common.obs_clipper import ObsClipperAdapter
from app.adapters.common.zimaos_client import ZimaOsHttpAdapter
from app.adapters.mock.mock_clipper import MockClipperAdapter
from app.adapters.mock.mock_system import MockSystemAdapter
from app.adapters.mock.null_audio import NullAudioAdapter
from app.adapters.mock.null_vision import NullVisionAdapter
from app.agent.langchain_agent import LangChainOSAgent
from app.core.config import AppSettings, settings
from app.ports.agent import IntentAgentPort
from app.ports.audio import AudioPlaybackPort, AudioPort
from app.ports.clipper import ClipperPort
from app.ports.flight import AirspaceRadarPort
from app.ports.media import MediaKeysPort
from app.ports.server import RemoteServerPort
from app.ports.system import (
    InstanceLockPort,
    SystemPowerPort,
    TrashPort,
    WindowInspectionPort,
)
from app.ports.vision import ScreenVisionPort

logger = logging.getLogger("glados.core.modules")


class PlatformModule(Module):
    """Binds ports to concrete adapters dynamically determined by OS platform and runtime flags."""

    def __init__(self, app_settings: AppSettings | None = None) -> None:
        self.settings = app_settings or settings

    def configure(self, binder: Binder) -> None:
        """Configures interface bindings for the dependency injection container."""
        # 1. Base Configuration and Lock
        binder.bind(AppSettings, to=self.settings, scope=singleton)
        binder.bind(InstanceLockPort, to=FileInstanceLock, scope=singleton)

        # 2. Remote homelab, airspace radar, and conversational agent integrations
        binder.bind(RemoteServerPort, to=ZimaOsHttpAdapter, scope=singleton)
        binder.bind(AirspaceRadarPort, to=FlightRadarAdapter, scope=singleton)
        binder.bind(IntentAgentPort, to=LangChainOSAgent, scope=singleton)

        # 3. Headless server mode overrides (e.g. CI runner, headless container, or explicit flag)
        if self.settings.headless_mode or self.settings.audio_backend == "null":
            logger.info("Initializing IoC container in Headless/Null mode.")
            null_audio = NullAudioAdapter()
            binder.bind(AudioPort, to=null_audio, scope=singleton)
            binder.bind(AudioPlaybackPort, to=null_audio, scope=singleton)
            binder.bind(ScreenVisionPort, to=NullVisionAdapter, scope=singleton)
            binder.bind(ClipperPort, to=MockClipperAdapter, scope=singleton)

            mock_sys = MockSystemAdapter()
            binder.bind(SystemPowerPort, to=mock_sys, scope=singleton)
            binder.bind(TrashPort, to=mock_sys, scope=singleton)
            binder.bind(WindowInspectionPort, to=mock_sys, scope=singleton)

            # Bind media keys to avoid unbound interface
            if sys.platform == "win32":
                from app.adapters.windows.media import WindowsMediaKeysAdapter

                binder.bind(MediaKeysPort, to=WindowsMediaKeysAdapter, scope=singleton)
            else:
                from app.adapters.linux.media import LinuxMediaKeysAdapter

                binder.bind(MediaKeysPort, to=LinuxMediaKeysAdapter, scope=singleton)
            return

        # 4. Windows Platform Adapters
        if sys.platform == "win32":
            logger.info("Binding Windows concrete OS adapters.")
            from app.adapters.windows.audio import WindowsAudioAdapter
            from app.adapters.windows.media import WindowsMediaKeysAdapter
            from app.adapters.windows.playback import WindowsAudioPlaybackAdapter
            from app.adapters.windows.system import WindowsSystemAdapter
            from app.adapters.windows.window import WindowsWindowInspectAdapter

            binder.bind(AudioPort, to=WindowsAudioAdapter, scope=singleton)
            binder.bind(AudioPlaybackPort, to=WindowsAudioPlaybackAdapter, scope=singleton)
            binder.bind(MediaKeysPort, to=WindowsMediaKeysAdapter, scope=singleton)

            win_sys = WindowsSystemAdapter()
            binder.bind(SystemPowerPort, to=win_sys, scope=singleton)
            binder.bind(TrashPort, to=win_sys, scope=singleton)
            binder.bind(WindowInspectionPort, to=WindowsWindowInspectAdapter, scope=singleton)

            binder.bind(ClipperPort, to=ObsClipperAdapter, scope=singleton)
            binder.bind(ScreenVisionPort, to=GeminiVisionAdapter, scope=singleton)
            return

        # 5. Linux Platform Adapters
        if sys.platform.startswith("linux"):
            logger.info("Binding Linux concrete OS adapters.")
            from app.adapters.linux.audio import LinuxAudioAdapter
            from app.adapters.linux.media import LinuxMediaKeysAdapter
            from app.adapters.linux.playback import LinuxAudioPlaybackAdapter
            from app.adapters.linux.system import LinuxSystemAdapter
            from app.adapters.linux.window import LinuxWindowInspectAdapter

            binder.bind(AudioPort, to=LinuxAudioAdapter, scope=singleton)
            binder.bind(AudioPlaybackPort, to=LinuxAudioPlaybackAdapter, scope=singleton)
            binder.bind(MediaKeysPort, to=LinuxMediaKeysAdapter, scope=singleton)

            linux_sys = LinuxSystemAdapter()
            binder.bind(SystemPowerPort, to=linux_sys, scope=singleton)
            binder.bind(TrashPort, to=linux_sys, scope=singleton)
            binder.bind(WindowInspectionPort, to=LinuxWindowInspectAdapter, scope=singleton)

            binder.bind(ClipperPort, to=ObsClipperAdapter, scope=singleton)
            binder.bind(ScreenVisionPort, to=GeminiVisionAdapter, scope=singleton)
            return

        # 6. Darwin / macOS / Other platform fallback
        logger.info("Binding fallback OS adapters for platform %s.", sys.platform)
        null_audio = NullAudioAdapter()
        binder.bind(AudioPort, to=null_audio, scope=singleton)
        binder.bind(AudioPlaybackPort, to=null_audio, scope=singleton)
        binder.bind(ScreenVisionPort, to=NullVisionAdapter, scope=singleton)
        binder.bind(ClipperPort, to=MockClipperAdapter, scope=singleton)

        mock_sys = MockSystemAdapter()
        binder.bind(SystemPowerPort, to=mock_sys, scope=singleton)
        binder.bind(TrashPort, to=mock_sys, scope=singleton)
        binder.bind(WindowInspectionPort, to=mock_sys, scope=singleton)
        from app.adapters.linux.media import LinuxMediaKeysAdapter

        binder.bind(MediaKeysPort, to=LinuxMediaKeysAdapter, scope=singleton)
