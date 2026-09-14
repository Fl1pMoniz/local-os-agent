"""Headless vision adapter implementing ScreenVisionPort."""

from __future__ import annotations

import logging

from app.ports.vision import ScreenVisionPort

logger = logging.getLogger("glados.adapters.mock.vision")


class NullVisionAdapter(ScreenVisionPort):
    """Fallback vision adapter for headless servers without physical displays."""

    def capture_screen(self) -> str:
        """Returns empty string indicating no display server is attached."""
        logger.debug("NullVisionAdapter: capture_screen called in headless mode.")
        return ""

    def analyze_screen(self, prompt: str) -> tuple[bool, str]:
        """Provides informative notice for display requests in headless mode."""
        logger.debug("NullVisionAdapter: analyze_screen called with prompt: %s", prompt)
        return (
            True,
            "Headless server active. Visual optical sensors are unavailable without an attached display.",
        )
