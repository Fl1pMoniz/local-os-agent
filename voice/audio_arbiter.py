"""Central audio arbiter ensuring strict mutual exclusion across all audio playback subsystems."""

import logging
import threading

logger = logging.getLogger("local_os_agent.voice.audio_arbiter")

# Global re-entrant lock acquired by any active audio playback (TTS, Soundboard, Songs, SFX)
GLOBAL_AUDIO_LOCK = threading.RLock()


def stop_all_audio() -> None:
    """
    Immediately stops all audio playback and clears queues across all subsystems:
    1. Text-To-Speech engine (voice.tts) - aborts MCI and purges SAPI5.
    2. Soundboard clips (tools.soundboard).
    3. Songs (tools.songs).
    4. SFX (tools.sfx).
    """
    try:
        from voice.tts import tts_engine

        tts_engine.stop()
    except Exception as e:
        logger.debug("Error stopping TTS: %s", e)

    try:
        from tools.soundboard import _stop_mci_soundboard

        _stop_mci_soundboard()
    except Exception as e:
        logger.debug("Error stopping soundboard: %s", e)

    try:
        from tools.songs import stop_song

        stop_song()
    except Exception as e:
        logger.debug("Error stopping songs: %s", e)

    try:
        from tools.sfx import stop_sfx

        stop_sfx()
    except Exception as e:
        logger.debug("Error stopping sfx: %s", e)
