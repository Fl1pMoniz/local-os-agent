"""Optical screen analysis adapter implementing ScreenVisionPort."""

from __future__ import annotations

import logging
from typing import Any

from app.ports.vision import ScreenVisionPort

logger = logging.getLogger("glados.adapters.vision")


class GeminiVisionAdapter(ScreenVisionPort):
    """Optical screen grabber and multimodal image analyzer."""

    def capture_screen(self) -> str:
        """Captures display and saves JPG artifact, returning file path."""
        from tools import vision

        filepath, _ = vision.capture_screen_image()
        return str(filepath) if filepath else ""

    def analyze_screen(self, prompt: str) -> tuple[bool, str]:
        """Analyzes active display content using multimodal vision model."""
        from tools import vision

        result: dict[str, Any] = vision.analyze_screen(prompt=prompt)
        success = result.get("success", False)
        output = result.get("analysis", result.get("message", "Analysis failed."))
        return success, output
