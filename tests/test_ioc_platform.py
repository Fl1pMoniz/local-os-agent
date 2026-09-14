"""Unit tests for Dependency Injection (IoC) container and platform resolution."""

from __future__ import annotations

import sys
import unittest
from pathlib import Path
from unittest.mock import patch

from app.adapters.common.file_lock import FileInstanceLock
from app.adapters.mock.mock_clipper import MockClipperAdapter
from app.adapters.mock.mock_system import MockSystemAdapter
from app.adapters.mock.null_audio import NullAudioAdapter
from app.adapters.mock.null_vision import NullVisionAdapter
from app.core.config import AppSettings
from app.core.container import create_container, get_container, reset_container
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


class TestIoCPlatform(unittest.TestCase):
    """Test suite verifying Inversion of Control bindings and dynamic OS adapter resolution."""

    def setUp(self) -> None:
        reset_container()

    def tearDown(self) -> None:
        reset_container()

    def test_default_container_resolution(self) -> None:
        """Verifies that the default container resolves all registered port contracts."""
        container = get_container()

        # Verify configuration and single-instance lock bindings
        cfg = container.get(AppSettings)
        self.assertIsInstance(cfg, AppSettings)

        lock = container.get(InstanceLockPort)
        self.assertIsInstance(lock, InstanceLockPort)

        # Verify common remote integrations
        radar = container.get(AirspaceRadarPort)
        self.assertIsInstance(radar, AirspaceRadarPort)

        server = container.get(RemoteServerPort)
        self.assertIsInstance(server, RemoteServerPort)

        # Verify core OS hardware ports
        audio = container.get(AudioPort)
        self.assertIsInstance(audio, AudioPort)

        playback = container.get(AudioPlaybackPort)
        self.assertIsInstance(playback, AudioPlaybackPort)

        media = container.get(MediaKeysPort)
        self.assertIsInstance(media, MediaKeysPort)

        power = container.get(SystemPowerPort)
        self.assertIsInstance(power, SystemPowerPort)

        trash = container.get(TrashPort)
        self.assertIsInstance(trash, TrashPort)

        window = container.get(WindowInspectionPort)
        self.assertIsInstance(window, WindowInspectionPort)

        clipper = container.get(ClipperPort)
        self.assertIsInstance(clipper, ClipperPort)

        vision = container.get(ScreenVisionPort)
        self.assertIsInstance(vision, ScreenVisionPort)

    def test_headless_mode_container_resolution(self) -> None:
        """Verifies container injects null and mock adapters when headless_mode is enabled."""
        headless_settings = AppSettings(headless_mode=True)
        container = create_container(app_settings=headless_settings)

        # Audio should be NullAudioAdapter
        audio = container.get(AudioPort)
        self.assertIsInstance(audio, NullAudioAdapter)
        self.assertTrue(audio.duck_audio())
        self.assertTrue(audio.restore_audio())
        self.assertEqual(audio.get_master_volume(), 0.5)

        # Vision should be NullVisionAdapter
        vision = container.get(ScreenVisionPort)
        self.assertIsInstance(vision, NullVisionAdapter)
        self.assertEqual(vision.capture_screen(), "")
        success, msg = vision.analyze_screen("test")
        self.assertTrue(success)
        self.assertIn("Headless", msg)

        # Clipper should be MockClipperAdapter
        clipper = container.get(ClipperPort)
        self.assertIsInstance(clipper, MockClipperAdapter)
        self.assertFalse(clipper.is_obs_running())

        # System should be MockSystemAdapter
        power = container.get(SystemPowerPort)
        self.assertIsInstance(power, MockSystemAdapter)
        self.assertTrue(power.lock_workstation())

        window = container.get(WindowInspectionPort)
        self.assertIsInstance(window, MockSystemAdapter)
        self.assertEqual(window.get_active_window_title(), "Headless Server Terminal")

    def test_linux_platform_bindings_mocked(self) -> None:
        """Verifies container selects Linux adapters when executed under Linux."""
        normal_settings = AppSettings(headless_mode=False)

        with patch.object(sys, "platform", "linux"):
            container = create_container(app_settings=normal_settings)

            from app.adapters.linux.audio import LinuxAudioAdapter
            from app.adapters.linux.media import LinuxMediaKeysAdapter
            from app.adapters.linux.playback import LinuxAudioPlaybackAdapter
            from app.adapters.linux.system import LinuxSystemAdapter
            from app.adapters.linux.window import LinuxWindowInspectAdapter

            self.assertIsInstance(container.get(AudioPort), LinuxAudioAdapter)
            self.assertIsInstance(container.get(AudioPlaybackPort), LinuxAudioPlaybackAdapter)
            self.assertIsInstance(container.get(MediaKeysPort), LinuxMediaKeysAdapter)
            self.assertIsInstance(container.get(SystemPowerPort), LinuxSystemAdapter)
            self.assertIsInstance(container.get(TrashPort), LinuxSystemAdapter)
            self.assertIsInstance(container.get(WindowInspectionPort), LinuxWindowInspectAdapter)

    def test_file_instance_lock_operations(self) -> None:
        """Verifies portalocker mutual exclusion on process instance locks."""
        import tempfile

        with tempfile.TemporaryDirectory() as tmp_dir:
            lock_path = Path(tmp_dir) / "test_glados.lock"

            lock1 = FileInstanceLock(lock_path=lock_path)
            self.assertTrue(lock1.acquire())
            self.assertTrue(lock1.is_locked())

            # A second lock instance targeting the exact same file should fail acquisition
            lock2 = FileInstanceLock(lock_path=lock_path)
            self.assertFalse(lock2.acquire())
            self.assertFalse(lock2.is_locked())

            # Releasing lock1 allows lock2 to acquire
            lock1.release()
            self.assertFalse(lock1.is_locked())

            self.assertTrue(lock2.acquire())
            self.assertTrue(lock2.is_locked())
            lock2.release()

    def test_settings_environment_variable_overrides(self) -> None:
        """Verifies 12-factor configuration environment variable parsing."""
        env = {
            "GLADOS_HOST": "0.0.0.0",
            "GLADOS_PORT": "9090",
            "GLADOS_HEADLESS": "true",
            "AUDIO_BACKEND": "null",
            "LLM_MODEL": "llama3.2:1b",
        }
        with patch.dict("os.environ", env):
            custom_settings = AppSettings()
            self.assertEqual(custom_settings.host, "0.0.0.0")
            self.assertEqual(custom_settings.port, 9090)
            self.assertTrue(custom_settings.headless_mode)
            self.assertEqual(custom_settings.audio_backend, "null")
            self.assertEqual(custom_settings.llm_model, "llama3.2:1b")
