"""Dual-channel logging infrastructure for GLaDOS.

Separates user-facing terminal presentation (clean stdout stream) from exhaustive
system diagnostics (rotating debug log file with timestamps, line numbers, and thread IDs).
"""

from __future__ import annotations

import logging
import sys
from logging.handlers import RotatingFileHandler
from pathlib import Path

from app.core.config import settings

UI_LOGGER_NAME = "glados.ui"


class UIConsoleFormatter(logging.Formatter):
    """Clean, human-readable terminal formatter free of emojis and debugging noise."""

    def format(self, record: logging.LogRecord) -> str:
        if record.levelno >= logging.ERROR:
            return f"[ERROR] {record.getMessage()}"
        if record.levelno >= logging.WARNING:
            return f"[WARN] {record.getMessage()}"
        return record.getMessage()


def setup_logging(
    logs_dir: Path | None = None,
    console_level: int = logging.INFO,
    file_level: int = logging.DEBUG,
) -> None:
    """Configures root logger with dual console and rotating file channels."""
    target_logs_dir = logs_dir or settings.logs_dir
    try:
        target_logs_dir.mkdir(parents=True, exist_ok=True)
    except OSError:
        pass

    root = logging.getLogger()
    root.setLevel(logging.DEBUG)

    # Clear existing handlers to prevent duplicate lines
    for handler in list(root.handlers):
        root.removeHandler(handler)

    # Channel 1: Clean Terminal Console Output
    console_handler = logging.StreamHandler(sys.stdout)
    console_handler.setLevel(console_level)
    console_handler.setFormatter(UIConsoleFormatter())
    root.addHandler(console_handler)

    # Channel 2: Rotating Debug Log File
    debug_log_path = target_logs_dir / "glados_debug.log"
    try:
        file_handler = RotatingFileHandler(
            filename=str(debug_log_path),
            maxBytes=5 * 1024 * 1024,  # 5 MB per segment
            backupCount=5,
            encoding="utf-8",
        )
        file_handler.setLevel(file_level)
        file_formatter = logging.Formatter(
            "%(asctime)s.%(msecs)03d [%(levelname)s] [%(threadName)s] %(name)s (%(filename)s:%(lineno)d): %(message)s",
            datefmt="%Y-%m-%d %H:%M:%S",
        )
        file_handler.setFormatter(file_formatter)
        root.addHandler(file_handler)
    except OSError as exc:
        logging.getLogger(UI_LOGGER_NAME).warning(
            "Unable to initialize rotating file logger at %s: %s", debug_log_path, exc
        )


def get_ui_logger() -> logging.Logger:
    """Retrieves dedicated user-facing terminal logger."""
    return logging.getLogger(UI_LOGGER_NAME)
