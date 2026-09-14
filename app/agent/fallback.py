"""Offline deterministic survival command resolver.

Provides zero-latency, offline regex intercepts for mission-critical operations
such as emergency audio muting, session locking, and hardware diagnostics, ensuring
uninterrupted local control even when the LLM service is offline or unreachable.
"""

from __future__ import annotations

import logging
import re
from typing import NamedTuple

logger = logging.getLogger("glados.agent.fallback")


class FallbackResult(NamedTuple):
    tool: str
    args: dict[str, object]
    response: str


# Pre-compiled deterministic intent patterns
RE_MUTE = re.compile(r"^(?:mute|unmute|silenciar|mudo|mutar|desmutar)$", re.IGNORECASE)
RE_STOP = re.compile(
    r"^(?:stop|stop song|stop music|stop audio|shut up|parar|cancela|silence)$", re.IGNORECASE
)
RE_LOCK = re.compile(
    r"^(?:lock|lock screen|lock pc|lock computer|lock workstation|bloquear|trancar tela)$",
    re.IGNORECASE,
)
RE_VOL_UP = re.compile(
    r"^(?:volume up|louder|increase volume|turn it up|sobe o volume|aumenta o volume)$",
    re.IGNORECASE,
)
RE_VOL_DOWN = re.compile(
    r"^(?:volume down|quieter|lower volume|turn it down|abaixa o volume|diminui o volume)$",
    re.IGNORECASE,
)
RE_VOL_EXACT = re.compile(r"^(?:set|put)?\s*volume\s*(?:to|at|para)?\s*(\d{1,3})%?$", re.IGNORECASE)
RE_STATS = re.compile(
    r"^(?:stats|system stats|pc stats|hardware stats|status do sistema|diagnostico)$",
    re.IGNORECASE,
)
RE_SCREENSHOT = re.compile(
    r"^(?:screenshot|take screenshot|capture screen|tirar print|print da tela)$", re.IGNORECASE
)
RE_RECYCLE = re.compile(
    r"^(?:empty recycle bin|clean recycle bin|esvaziar lixeira|limpar lixeira)$", re.IGNORECASE
)


class OfflineFallbackResolver:
    """Evaluates input prompts against deterministic patterns before dispatching to LLM."""

    def resolve(self, prompt: str) -> FallbackResult | None:
        """Attempts to resolve critical survival commands without LLM intervention."""
        clean = prompt.strip().lower()

        # 1. Emergency Audio Stop / Silence
        if RE_STOP.match(clean):
            return FallbackResult(
                tool="stop_song",
                args={},
                response="Audio playback halted immediately per survival protocol.",
            )

        # 2. Mute Toggle
        if RE_MUTE.match(clean):
            return FallbackResult(
                tool="mute_toggle",
                args={},
                response="Master audio state toggled.",
            )

        # 3. Workstation Session Lock
        if RE_LOCK.match(clean):
            return FallbackResult(
                tool="lock_workstation",
                args={},
                response="Workstation locked. Test environment secured.",
            )

        # 4. Exact Volume Adjustment
        if match := RE_VOL_EXACT.search(clean):
            lvl = int(match.group(1))
            bounded = max(0, min(100, lvl))
            return FallbackResult(
                tool="set_volume",
                args={"level": bounded},
                response=f"Master volume adjusted to {bounded} percent.",
            )

        # 5. Relative Volume Adjustments
        if RE_VOL_UP.search(clean):
            return FallbackResult(
                tool="change_volume_relative",
                args={"delta": 10},
                response="Master volume increased by 10 percent.",
            )
        if RE_VOL_DOWN.search(clean):
            return FallbackResult(
                tool="change_volume_relative",
                args={"delta": -10},
                response="Master volume decreased by 10 percent.",
            )

        # 6. System Diagnostics
        if RE_STATS.match(clean):
            return FallbackResult(
                tool="get_system_stats",
                args={},
                response="Retrieving Aperture Science facility hardware statistics.",
            )

        # 7. Screen Capture
        if RE_SCREENSHOT.match(clean):
            return FallbackResult(
                tool="take_screenshot",
                args={},
                response="Screen capture logged to optical archives.",
            )

        # 8. Recycle Bin Purge
        if RE_RECYCLE.match(clean):
            return FallbackResult(
                tool="empty_recycle_bin",
                args={},
                response="Permanent trash purge protocol initiated.",
            )

        return None
