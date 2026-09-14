"""Unit tests verifying safety protocols in container, headless, and ZimaOS environments.

Ensures that tests or agent models executing in ZimaOS/Docker NEVER suspend the host,
never lock desktop screens, and never terminate critical homelab daemons (Ollama, Docker, Jellyfin).
"""

import os
import unittest
from unittest.mock import patch

from app.adapters.linux.system import LinuxSystemAdapter
from tools import system


class TestZimaOSSafetyProtocols(unittest.TestCase):
    """Verifies that power, lock, and process operations safely degrade in container/server mode."""

    def test_lock_workstation_in_container_mode_is_safe_noop(self) -> None:
        """Verifies lock_workstation safely returns True without invoking system lock."""
        with patch.dict(os.environ, {"CONTAINER_MODE": "true"}):
            success, msg = system.lock_workstation()
            self.assertTrue(success)
            self.assertIn("bypassed", msg.lower())

    def test_sleep_pc_in_container_mode_is_strictly_inhibited(self) -> None:
        """Verifies sleep_pc is blocked to prevent server suspend."""
        with patch.dict(os.environ, {"CONTAINER_MODE": "true"}):
            success, msg = system.sleep_pc()
            self.assertFalse(success)
            self.assertIn("inhibited", msg.lower())

    def test_shutdown_in_container_mode_is_strictly_inhibited(self) -> None:
        """Verifies shutdown is blocked to prevent server halt."""
        with patch.dict(os.environ, {"CONTAINER_MODE": "true"}):
            success, msg = system.shutdown(delay_seconds=0)
            self.assertFalse(success)
            self.assertIn("inhibited", msg.lower())

    def test_minimize_all_windows_in_container_mode(self) -> None:
        """Verifies window minimization is safely omitted without desktop display."""
        with patch.dict(os.environ, {"CONTAINER_MODE": "true"}):
            success, msg = system.minimize_all_windows()
            self.assertTrue(success)
            self.assertIn("omitted", msg.lower())

    def test_kill_process_protects_zimaos_and_container_daemons(self) -> None:
        """Verifies kill_process refuses to terminate Ollama, Docker, Python, or ZimaOS services."""
        protected_targets = [
            "ollama",
            "docker",
            "dockerd",
            "python",
            "systemd",
            "init",
            "casaos",
            "zimaos",
            "jellyfin",
            "homeassistant",
        ]
        for target in protected_targets:
            success, msg = system.kill_process(target)
            self.assertFalse(success, f"Should not allow killing {target}")
            self.assertIn("critical", msg.lower())

    def test_kill_process_protects_low_pids(self) -> None:
        """Verifies PID 0, 1, and 4 are strictly untouchable."""
        for pid in (0, 1, 4):
            success, msg = system.kill_process(pid)
            self.assertFalse(success)
            self.assertIn("cannot be terminated", msg.lower())

    def test_linux_adapter_inhibits_power_and_session_actions(self) -> None:
        """Verifies LinuxSystemAdapter respects container/server mode without spawning subprocesses."""
        adapter = LinuxSystemAdapter()
        with (
            patch.dict(os.environ, {"CONTAINER_MODE": "true"}),
            patch("subprocess.run") as mock_sub,
        ):
            # Lock workstation must return True without calling loginctl or xdg-screensaver
            self.assertTrue(adapter.lock_workstation())
            mock_sub.assert_not_called()

            # Sleep must return False without calling systemctl suspend
            self.assertFalse(adapter.sleep())
            mock_sub.assert_not_called()

            # Shutdown must return False without calling systemctl poweroff
            self.assertFalse(adapter.shutdown())
            mock_sub.assert_not_called()

            # Restart must return False without calling systemctl reboot
            self.assertFalse(adapter.restart())
            mock_sub.assert_not_called()
