"""Application configuration based on Pydantic BaseSettings.

Provides 12-factor configuration support with environment variable overrides,
type validation, and cross-platform path resolution.
"""

from __future__ import annotations

import os
from pathlib import Path
from typing import Literal

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


def get_default_data_dir() -> Path:
    """Resolve the base data storage directory based on environment or OS conventions."""
    if env_dir := os.getenv("GLADOS_DATA_DIR"):
        return Path(env_dir).resolve()
    return Path.cwd() / "data"


def get_default_captures_dir() -> Path:
    """Resolve the screen and audio captures directory."""
    if env_dir := os.getenv("GLADOS_CAPTURES_DIR"):
        return Path(env_dir).resolve()
    return Path.cwd() / "captures"


def get_default_logs_dir() -> Path:
    """Resolve the application logs directory."""
    if env_dir := os.getenv("GLADOS_LOGS_DIR"):
        return Path(env_dir).resolve()
    return Path.cwd() / "logs"


def get_default_lock_file() -> Path:
    """Resolve the single-instance lock file path."""
    if env_file := os.getenv("GLADOS_LOCK_FILE"):
        return Path(env_file).resolve()
    return Path.cwd() / "glados.lock"


class AppSettings(BaseSettings):
    """Strongly-typed application settings loaded from environment and defaults."""

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
        populate_by_name=True,
    )

    # Server and Network Configuration
    host: str = Field(default="127.0.0.1", alias="GLADOS_HOST")
    port: int = Field(default=5000, alias="GLADOS_PORT")
    open_browser: bool = Field(default=True, alias="GLADOS_OPEN_BROWSER")
    headless_mode: bool = Field(default=False, alias="GLADOS_HEADLESS")

    # LLM Settings
    llm_base_url: str = Field(default="http://localhost:11434/v1", alias="LLM_BASE_URL")
    llm_api_key: str = Field(default="ollama", alias="LLM_API_KEY")
    llm_model: str = Field(default="glados:3b", alias="LLM_MODEL")
    llm_temperature: float = Field(default=0.2, alias="LLM_TEMPERATURE")
    llm_timeout: float = Field(default=45.0, alias="LLM_TIMEOUT")
    llm_num_ctx: int = Field(default=2048, alias="LLM_NUM_CTX")
    llm_max_tokens: int = Field(default=120, alias="LLM_MAX_TOKENS")

    # Storage Paths
    data_dir: Path = Field(default_factory=get_default_data_dir)
    captures_dir: Path = Field(default_factory=get_default_captures_dir)
    logs_dir: Path = Field(default_factory=get_default_logs_dir)
    lock_file: Path = Field(default_factory=get_default_lock_file)
    audio_cache_dir: Path = Field(default_factory=lambda: get_default_captures_dir() / "audio")

    # Audio & Voice Settings
    enable_tts: bool = Field(default=True, alias="ENABLE_TTS")
    voice_recognition_enabled: bool = Field(default=False, alias="VOICE_RECOGNITION")
    audio_backend: Literal["auto", "windows", "linux", "null"] = Field(
        default="auto", alias="AUDIO_BACKEND"
    )
    tts_voice: str = Field(default="glados", alias="TTS_VOICE")
    tts_rate: str = Field(default="-4%", alias="TTS_RATE")
    tts_pitch: str = Field(default="+4Hz", alias="TTS_PITCH")
    stt_engine: str = Field(default="whisper", alias="STT_ENGINE")
    whisper_model: str = Field(default="base.en", alias="WHISPER_MODEL")
    whisper_device: str = Field(default="cuda", alias="WHISPER_DEVICE")
    whisper_vram_limit_mb: int = Field(default=1024, alias="WHISPER_VRAM_LIMIT_MB")
    stt_language: str = Field(default="en", alias="STT_LANGUAGE")
    wake_word: str = Field(default="glados", alias="WAKE_WORD")
    require_wake_word: bool = Field(default=True, alias="REQUIRE_WAKE_WORD")

    # Steam Game Discovery
    custom_steam_path: str | None = Field(default=None, alias="STEAM_CUSTOM_PATH")

    # External Integrations
    obs_host: str = Field(default="localhost", alias="OBS_HOST")
    obs_port: int = Field(default=4455, alias="OBS_PORT")
    obs_password: str | None = Field(default=None, alias="OBS_PASSWORD")
    zimaos_host: str = Field(default="http://zimaos.local", alias="ZIMAOS_HOST")
    zimaos_api_key: str | None = Field(default=None, alias="ZIMAOS_API_KEY")
    gemini_api_key: str | None = Field(default=None, alias="GEMINI_API_KEY")

    # CLI Operational Flags
    cli_mode: bool = False

    # Guardrails
    sensitive_tools: tuple[str, ...] = (
        "kill_process",
        "shutdown",
        "sleep_pc",
    )

    def model_post_init(self, __context: object) -> None:
        """Ensure required operational directories exist upon initialization."""
        try:
            self.data_dir.mkdir(parents=True, exist_ok=True)
            self.captures_dir.mkdir(parents=True, exist_ok=True)
            self.logs_dir.mkdir(parents=True, exist_ok=True)
            self.audio_cache_dir.mkdir(parents=True, exist_ok=True)
        except OSError:
            # Fallback gracefully if filesystem permissions prevent creation
            pass

    @property
    def voice_enabled(self) -> bool:
        """Determines if voice output should play given current runtime mode."""
        return self.enable_tts and not self.cli_mode and not self.headless_mode


# Singleton default configuration instance
settings = AppSettings()
