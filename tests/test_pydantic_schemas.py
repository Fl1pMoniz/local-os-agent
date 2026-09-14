"""Unit tests for LangChain Pydantic parameter schemas."""

from __future__ import annotations

import unittest

from pydantic import ValidationError

from app.agent.tools import (
    CaptureClipInput,
    LogWaterInput,
    PlayYouTubeInput,
    RelativeVolumeInput,
    SetTimerInput,
    VolumeInput,
)


class TestPydanticSchemas(unittest.TestCase):
    """Test suite validating input bounds and type checking for tool schemas."""

    def test_volume_bounds_valid(self) -> None:
        """Verifies valid volume levels accept properly."""
        valid_low = VolumeInput(level=0)
        valid_high = VolumeInput(level=100)
        valid_mid = VolumeInput(level=50)
        self.assertEqual(valid_low.level, 0)
        self.assertEqual(valid_high.level, 100)
        self.assertEqual(valid_mid.level, 50)

    def test_volume_bounds_invalid(self) -> None:
        """Verifies out-of-bounds volume raises ValidationError."""
        with self.assertRaises(ValidationError):
            VolumeInput(level=-1)
        with self.assertRaises(ValidationError):
            VolumeInput(level=101)

    def test_relative_volume_signed(self) -> None:
        """Verifies delta allows both positive and negative values."""
        up = RelativeVolumeInput(delta=15)
        down = RelativeVolumeInput(delta=-20)
        self.assertEqual(up.delta, 15)
        self.assertEqual(down.delta, -20)

    def test_timer_bounds(self) -> None:
        """Verifies timer requires positive duration."""
        valid = SetTimerInput(seconds=60, label="Reactor Stability")
        self.assertEqual(valid.seconds, 60)
        self.assertEqual(valid.label, "Reactor Stability")

        with self.assertRaises(ValidationError):
            SetTimerInput(seconds=0)
        with self.assertRaises(ValidationError):
            SetTimerInput(seconds=-10)

    def test_capture_clip_bounds(self) -> None:
        """Verifies game clip seconds constraint (5 to 120s)."""
        valid = CaptureClipInput(seconds=30)
        self.assertEqual(valid.seconds, 30)

        with self.assertRaises(ValidationError):
            CaptureClipInput(seconds=2)
        with self.assertRaises(ValidationError):
            CaptureClipInput(seconds=300)

    def test_youtube_input_defaults(self) -> None:
        """Verifies YouTube defaults music to False."""
        inp = PlayYouTubeInput(query="Portal Radio 10 Hours")
        self.assertEqual(inp.query, "Portal Radio 10 Hours")
        self.assertFalse(inp.music)

        music_inp = PlayYouTubeInput(query="Jonathan Coulton", music=True)
        self.assertTrue(music_inp.music)

    def test_hydration_logging_bounds(self) -> None:
        """Verifies water consumption validation bounds."""
        valid = LogWaterInput(amount_ml=500)
        self.assertEqual(valid.amount_ml, 500)

        with self.assertRaises(ValidationError):
            LogWaterInput(amount_ml=0)
        with self.assertRaises(ValidationError):
            LogWaterInput(amount_ml=10000)
