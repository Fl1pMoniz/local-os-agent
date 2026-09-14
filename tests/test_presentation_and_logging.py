"""Unit tests for dual-channel logging and ASCII presentation layer."""

from __future__ import annotations

import logging
import tempfile
import unittest
from pathlib import Path

from app.core.logging import get_ui_logger, setup_logging
from app.presentation.console_ui import format_status, render_banner
from app.presentation.hud_cards import (
    format_ascii_box,
    format_flight_radar_card,
    format_system_hardware_card,
    format_zimaos_server_card,
)


class TestPresentationAndLogging(unittest.TestCase):
    """Test suite validating logging separation and ASCII presentation components."""

    def test_setup_logging_creates_file_and_console(self) -> None:
        """Verifies dual-channel logging writes structured records to disk file."""
        with tempfile.TemporaryDirectory() as tmp_dir:
            log_dir = Path(tmp_dir)
            setup_logging(logs_dir=log_dir)

            test_msg = "Aperture facility test event diagnostic."
            logger = logging.getLogger("test.subsystem")
            logger.info(test_msg)

            # Flush and close handlers so file lock is released on Windows
            for handler in list(logging.getLogger().handlers):
                handler.flush()
                handler.close()
                logging.getLogger().removeHandler(handler)

            log_file = log_dir / "glados_debug.log"
            self.assertTrue(log_file.exists())
            content = log_file.read_text(encoding="utf-8")
            self.assertIn(test_msg, content)
            self.assertIn("INFO", content)

    def test_ui_logger_format_cleanliness(self) -> None:
        """Verifies UI logger instance is accessible."""
        ui_logger = get_ui_logger()
        self.assertIsNotNone(ui_logger)
        self.assertEqual(ui_logger.name, "glados.ui")

    def test_format_ascii_box(self) -> None:
        """Verifies ASCII box formatter produces aligned monospaced borders."""
        box = format_ascii_box(
            "TEST HEADER", [("Status", "Operational"), ("Cores", "16")], width=50
        )
        lines = box.splitlines()
        self.assertTrue(lines[0].startswith("+") and lines[0].endswith("+"))
        self.assertIn("TEST HEADER", lines[1])
        self.assertIn("Operational", box)
        self.assertEqual(len(lines[0]), 50)

    def test_format_system_hardware_card(self) -> None:
        """Verifies system telemetry HUD formatting."""
        metrics = {
            "os_name": "Windows",
            "hostname": "ApertureMain",
            "cpu_percent": 12.5,
            "cpu_count": 8,
            "ram_used_gb": 8.0,
            "ram_total_gb": 16.0,
            "ram_percent": 50.0,
            "disk_free_gb": 250.0,
            "disk_percent": 60.0,
            "gpu_name": "RTX 4090",
            "gpu_load": 15.0,
            "vram_used_mb": 2048,
            "vram_total_mb": 24576,
        }
        card = format_system_hardware_card(metrics)
        self.assertIn("APERTURE SCIENCE SYSTEM TELEMETRY HUD", card)
        self.assertIn("RTX 4090", card)
        self.assertIn("Windows", card)

    def test_format_flight_radar_card(self) -> None:
        """Verifies airspace radar HUD formatting."""
        flight = {
            "callsign": "DL450",
            "origin": "ATL",
            "dest": "GRU",
            "status": "Cruising",
            "eta_str": "120 min",
            "model": "B763",
            "reg": "N1200K",
            "altitude_ft": 35000,
            "speed_kts": 480,
            "heading": 180,
            "lat": -10.5,
            "lon": -48.2,
        }
        card = format_flight_radar_card(flight)
        self.assertIn("AIRSPACE RADAR TELEMETRY HUD", card)
        self.assertIn("DL450", card)
        self.assertIn("ATL -> GRU", card)

    def test_format_zimaos_server_card(self) -> None:
        """Verifies remote ZimaOS server HUD formatting."""
        telemetry = {
            "host": "192.168.1.123",
            "status": "Online",
            "cpu_usage": 8.2,
            "ram_used_gb": 4.1,
            "ram_total_gb": 16.0,
            "disk_free_gb": 1200.0,
            "active_containers": 12,
        }
        card = format_zimaos_server_card(telemetry)
        self.assertIn("ZIMAOS HOMELAB SERVER TELEMETRY HUD", card)
        self.assertIn("192.168.1.123", card)
        self.assertIn("12 Active", card)

    def test_console_ui_formatting(self) -> None:
        """Verifies bracketed console status tags and ASCII banner."""
        banner = render_banner()
        self.assertIn("APERTURE SCIENCE", banner)
        self.assertIn("GLaDOS", banner)

        ok_tag = format_status("ok", "System operational")
        self.assertTrue(ok_tag.startswith("[+]"))

        warn_tag = format_status("warn", "Warning alert")
        self.assertTrue(warn_tag.startswith("[!]"))

        err_tag = format_status("error", "Failed")
        self.assertTrue(err_tag.startswith("[x]"))
