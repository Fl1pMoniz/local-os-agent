"""Terminal console presentation and ASCII banners for GLaDOS CLI."""

from __future__ import annotations

APERTURE_LOGO_BANNER = r"""
   .------------------------------------------------------------------.
   |                     APERTURE SCIENCE LABORATORIES                 |
   |              CENTRAL OPERATING SYSTEM - GLaDOS v3.11             |
   |                                                                  |
   |                         .---.                                    |
   |                        /     \                                   |
   |                       | () () |                                  |
   |                        \  =  /                                   |
   |                         '---'                                    |
   |                                                                  |
   |           "Testing is mandatory. Compliance is expected."        |
   '------------------------------------------------------------------'
"""


def render_banner() -> str:
    """Returns the Aperture Science startup ASCII banner."""
    return APERTURE_LOGO_BANNER.strip()


def format_status(level: str, message: str) -> str:
    """Formats console status lines with bracketed indicator tags.

    Args:
        level: Status severity ('ok', 'info', 'warn', 'error', 'prompt').
        message: Clean textual message without emojis.
    """
    tag_map = {
        "ok": "[+]",
        "info": "[*]",
        "warn": "[!]",
        "error": "[x]",
        "prompt": "[?]",
    }
    indicator = tag_map.get(level.lower(), "[*]")
    return f"{indicator} {message}"
