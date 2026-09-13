"""Configuration module for the Local OS Agent."""

import os
from dataclasses import dataclass
from pathlib import Path


@dataclass
class AgentConfig:
    # LLM Settings (OpenAI compatible endpoint)
    llm_base_url: str = os.getenv("LLM_BASE_URL", "http://localhost:11434/v1")
    llm_api_key: str = os.getenv("LLM_API_KEY", "ollama")  # Ollama accepts any non-empty string
    llm_model: str = os.getenv("LLM_MODEL", "glados:3b")
    llm_temperature: float = float(os.getenv("LLM_TEMPERATURE", "0.2"))
    llm_timeout: float = float(os.getenv("LLM_TIMEOUT", "45.0"))
    llm_num_ctx: int = int(os.getenv("LLM_NUM_CTX", "2048"))  # Limit KV cache to 2k tokens (< 200MB VRAM)
    llm_max_tokens: int = int(os.getenv("LLM_MAX_TOKENS", "120"))  # Enforce concise responses

    # Project Directories
    base_dir: Path = Path(__file__).resolve().parent
    captures_dir: Path = base_dir / "captures"

    # Steam Settings (auto-detected if None)
    custom_steam_path: str | None = os.getenv("STEAM_CUSTOM_PATH", None)

    # Voice & Wake Word Settings
    enable_tts: bool = os.getenv("ENABLE_TTS", "true").lower() in ("true", "1", "yes")
    tts_voice: str = os.getenv("TTS_VOICE", "glados")
    tts_rate: str = os.getenv("TTS_RATE", "-4%")  # Deliberate, unhurried Portal 2 delivery
    tts_pitch: str = os.getenv("TTS_PITCH", "+4Hz")  # Ellen McLain GLaDOS tonal lift
    stt_language: str = os.getenv("STT_LANGUAGE", "en-US")
    wake_word: str = os.getenv("WAKE_WORD", "glados").lower()
    require_wake_word: bool = os.getenv("REQUIRE_WAKE_WORD", "true").lower() in ("true", "1", "yes")
    audio_cache_dir: Path = base_dir / "captures" / "audio"

    # Sensitive tools requiring user confirmation
    sensitive_tools: tuple[str, ...] = (
        "kill_process",
        "shutdown",
        "sleep_pc",
    )

    @property
    def voice_enabled(self) -> bool:
        return self.enable_tts

    def __post_init__(self) -> None:
        self.captures_dir.mkdir(parents=True, exist_ok=True)
        self.audio_cache_dir.mkdir(parents=True, exist_ok=True)


config = AgentConfig()

