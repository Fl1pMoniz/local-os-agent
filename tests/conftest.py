"""Shared pytest fixtures and test suite configuration.

Provides isolated temporary settings, headless mock dependency injection containers,
and clean lifecycle teardown across test runs.
"""

from __future__ import annotations

import tempfile
from collections.abc import Generator
from pathlib import Path
from unittest.mock import MagicMock

import pytest
from injector import Injector

from app.core.config import AppSettings
from app.core.container import create_container, reset_container


@pytest.fixture
def mock_temp_dir() -> Generator[Path, None, None]:
    """Provides an isolated temporary directory cleaned up after test execution."""
    with tempfile.TemporaryDirectory() as tmp:
        yield Path(tmp)


@pytest.fixture
def mock_settings(mock_temp_dir: Path) -> AppSettings:
    """Provides an AppSettings instance isolated to a temporary directory."""
    return AppSettings(
        data_dir=mock_temp_dir / "data",
        captures_dir=mock_temp_dir / "captures",
        logs_dir=mock_temp_dir / "logs",
        lock_file=mock_temp_dir / "glados_test.lock",
        headless_mode=True,
        audio_backend="null",
        enable_tts=False,
    )


@pytest.fixture
def mock_container(mock_settings: AppSettings) -> Generator[Injector, None, None]:
    """Provides a fresh Injector container configured with mock and headless adapters."""
    reset_container()
    container = create_container(app_settings=mock_settings)
    yield container
    reset_container()


@pytest.fixture
def mock_llm() -> MagicMock:
    """Provides a mocked ChatOpenAI instance for tool-calling agent tests."""
    mock = MagicMock()
    mock.bind_tools.return_value = mock
    return mock
