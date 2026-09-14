"""Tests validating pytest fixtures defined in conftest.py."""

from __future__ import annotations

from pathlib import Path
from unittest.mock import MagicMock

from injector import Injector

from app.adapters.mock.null_audio import NullAudioAdapter
from app.core.config import AppSettings
from app.ports.audio import AudioPort


def test_mock_settings_fixture(mock_settings: AppSettings, mock_temp_dir: Path) -> None:
    """Verifies that mock_settings is bound to the isolated temporary directory."""
    assert mock_settings.headless_mode is True
    assert mock_settings.audio_backend == "null"
    assert str(mock_temp_dir) in str(mock_settings.data_dir)


def test_mock_container_fixture(mock_container: Injector) -> None:
    """Verifies that mock_container resolves mock/headless adapters."""
    audio = mock_container.get(AudioPort)
    assert isinstance(audio, NullAudioAdapter)
    assert audio.duck_audio() is True


def test_mock_llm_fixture(mock_llm: MagicMock) -> None:
    """Verifies that mock_llm provides tool binding mock."""
    bound = mock_llm.bind_tools([])
    assert bound is not None
