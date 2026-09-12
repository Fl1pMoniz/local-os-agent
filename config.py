"""Configuration module for the Local OS Agent."""

import os
from dataclasses import dataclass
from pathlib import Path


@dataclass
class AgentConfig:
    # LLM Settings (OpenAI compatible endpoint)
    llm_base_url: str = os.getenv("LLM_BASE_URL", "http://localhost:11434/v1")
    llm_api_key: str = os.getenv("LLM_API_KEY", "ollama")  # Ollama accepts any non-empty string
    llm_model: str = os.getenv("LLM_MODEL", "llama3.2")
    llm_temperature: float = float(os.getenv("LLM_TEMPERATURE", "0.1"))
    llm_timeout: float = float(os.getenv("LLM_TIMEOUT", "60.0"))

    # Project Directories
    base_dir: Path = Path(__file__).resolve().parent
    captures_dir: Path = base_dir / "captures"

    # Steam Settings (auto-detected if None)
    custom_steam_path: str | None = os.getenv("STEAM_CUSTOM_PATH", None)

    # Sensitive tools requiring user confirmation
    sensitive_tools: tuple[str, ...] = (
        "kill_process",
        "shutdown",
        "sleep_pc",
    )

    def __post_init__(self) -> None:
        self.captures_dir.mkdir(parents=True, exist_ok=True)


config = AgentConfig()

