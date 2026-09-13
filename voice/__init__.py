"""Voice subsystem with lazy-loaded components to prevent VRAM and memory bloat in CLI mode."""

from typing import Any


from voice.audio_arbiter import GLOBAL_AUDIO_LOCK, stop_all_audio


def speak(text: str, wait: bool = False) -> None:
    """Convenience helper to speak text using the global TTS engine. No-op if TTS or voice is disabled."""
    from config import config
    if not config.voice_enabled or config.cli_mode:
        return
    from voice.tts import tts_engine
    tts_engine.speak(text, wait=wait)


def __getattr__(name: str) -> Any:
    """Lazy imports to prevent sounddevice, whisper, torch, or pyttsx3 loading when not needed."""
    if name == "VoiceListener":
        from voice.listener import VoiceListener
        return VoiceListener
    if name == "extract_wake_word_command":
        from voice.listener import extract_wake_word_command
        return extract_wake_word_command
    if name in ("TextToSpeech", "clean_text_for_speech", "tts_engine"):
        import voice.tts as tts
        return getattr(tts, name)
    if name in ("GLADOS_VOICELINES", "get_contextual_quip", "get_glados_quote"):
        import voice.glados_lines as lines
        return getattr(lines, name)
    raise AttributeError(f"module 'voice' has no attribute '{name}'")


__all__ = [
    "TextToSpeech",
    "VoiceListener",
    "tts_engine",
    "speak",
    "stop_all_audio",
    "GLOBAL_AUDIO_LOCK",
    "clean_text_for_speech",
    "extract_wake_word_command",
    "get_glados_quote",
    "get_contextual_quip",
    "GLADOS_VOICELINES",
]

