"""Optical screen capture and visual analysis port definitions."""

from __future__ import annotations

from typing import Protocol, runtime_checkable


@runtime_checkable
class ScreenVisionPort(Protocol):
    """Protocol for capturing display frames and optical inference analysis."""

    def capture_screen(self) -> str:
        """Captures active screen framebuffer and returns path to written image file."""
        ...

    def analyze_screen(self, prompt: str) -> tuple[bool, str]:
        """Captures active screen and queries multimodal vision LLM with prompt."""
        ...
