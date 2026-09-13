from voice.glados_lines import GLADOS_VOICELINES, get_contextual_quip, get_glados_quote
from voice.listener import VoiceListener, extract_wake_word_command
from voice.tts import TextToSpeech, clean_text_for_speech, tts_engine


def speak(text: str, wait: bool = False) -> None:
    """Convenience helper to speak text using the global TTS engine."""
    tts_engine.speak(text, wait=wait)


__all__ = [
    "TextToSpeech",
    "VoiceListener",
    "tts_engine",
    "speak",
    "clean_text_for_speech",
    "extract_wake_word_command",
    "get_glados_quote",
    "get_contextual_quip",
    "GLADOS_VOICELINES",
]

