"""Protocol 4 Component: Aperture Acoustic Synthesizer & Soundboard.
Plays iconic Aperture Science character dialogue (Cave Johnson, Wheatley, Space Core,
Turrets, Announcer) with automatic background audio ducking and ambient chamber modes.
"""

import asyncio
import ctypes
import logging
import pathlib
import threading
from typing import Any

from config import config
from tools import register_tool
from tools.audio_ducking import audio_ducked

logger = logging.getLogger("local_os_agent.tools.soundboard")

winmm = getattr(ctypes, "windll", None).winmm if hasattr(ctypes, "windll") else None
SOUNDBOARD_DIR = config.audio_cache_dir / "soundboard"
SOUNDBOARD_DIR.mkdir(parents=True, exist_ok=True)

MCI_SB_ALIAS = "glados_soundboard_player"
_sb_lock = threading.Lock()
_current_soundboard_thread: threading.Thread | None = None
_ambience_active = False

# Soundboard registry with speech profiles
SOUNDBOARD_ENTRIES: dict[str, dict[str, Any]] = {
    "lemons": {
        "speaker": "Cave Johnson",
        "title": "Combustible Lemons Rant",
        "voice": "en-US-GuyNeural",
        "rate": "+10%",
        "pitch": "-4Hz",
        "text": (
            "When life gives you lemons, don't make lemonade! Make life take the lemons back! "
            "Get mad! I don't want your damn lemons, what am I supposed to do with these? "
            "Demand to see life's manager! Make life rue the day it thought it could give Cave Johnson lemons! "
            "Do you know who I am? I'm the man who's gonna burn your house down! With the lemons! "
            "I'm gonna get my engineers to invent a combustible lemon that burns your house down!"
        ),
    },
    "wheatley_moron": {
        "speaker": "Wheatley",
        "title": "I AM NOT A MORON",
        "voice": "en-GB-RyanNeural",
        "rate": "+15%",
        "pitch": "+6Hz",
        "text": "I AM NOT A MORON! Could a moron punch you into this pit? Huh? Could a moron do that?!",
    },
    "wheatley_hello": {
        "speaker": "Wheatley",
        "title": "Management Core Greetings",
        "voice": "en-GB-RyanNeural",
        "rate": "+5%",
        "pitch": "+4Hz",
        "text": "Hello! Can you hear me? Speak up, I can't quite hear you. Hello! Anyone there?",
    },
    "space": {
        "speaker": "Space Core",
        "title": "SPAAACE!",
        "voice": "en-US-ChristopherNeural",
        "rate": "+30%",
        "pitch": "+12Hz",
        "text": "Space! Space! Gotta go to space! Yeah, yeah, yeah, space! Ba, ba, ba, space core in space!",
    },
    "neurotoxin": {
        "speaker": "GLaDOS",
        "title": "Neurotoxin Deployment Warning",
        "voice": "en-US-JennyNeural",
        "rate": "-5%",
        "pitch": "+5Hz",
        "text": (
            "Warning: The Enrichment Center has initiated the deadly neurotoxin countdown. "
            "You have thirty seconds to complete testing. Or stop breathing. Either outcome is acceptable."
        ),
    },
    "turret_sorry": {
        "speaker": "Aperture Turret",
        "title": "No Hard Feelings",
        "voice": "en-US-AnaNeural",
        "rate": "-10%",
        "pitch": "+16Hz",
        "text": "Target lost. No hard feelings. I don't blame you.",
    },
}


def _stop_mci_soundboard():
    """Stops any active soundboard clip playing via MCI."""
    if not winmm:
        return
    try:
        winmm.mciSendStringW(f"stop {MCI_SB_ALIAS}", None, 0, 0)
        winmm.mciSendStringW(f"close {MCI_SB_ALIAS}", None, 0, 0)
    except Exception:
        pass


def _synthesize_soundboard_clip(entry_key: str, dest_file: pathlib.Path) -> bool:
    """Uses edge_tts to generate audio with character specific modulation."""
    entry = SOUNDBOARD_ENTRIES.get(entry_key)
    if not entry:
        return False

    try:
        import edge_tts

        communicate = edge_tts.Communicate(
            text=entry["text"],
            voice=entry["voice"],
            rate=entry.get("rate", "+0%"),
            pitch=entry.get("pitch", "+0Hz"),
        )
        asyncio.run(communicate.save(str(dest_file)))
        return dest_file.exists() and dest_file.stat().st_size > 0
    except Exception as e:
        logger.error(f"Failed to synthesize soundboard clip '{entry_key}': {e}")
        return False


def _play_file_with_ducking(file_path: pathlib.Path):
    """Plays audio file with background audio ducking and global audio lock."""
    if not winmm:
        return
    try:
        from voice.tts import tts_engine

        tts_engine.stop()
    except Exception:
        pass

    try:
        from voice.audio_arbiter import GLOBAL_AUDIO_LOCK

        with GLOBAL_AUDIO_LOCK:
            with audio_ducked(target_fraction=0.15):
                _stop_mci_soundboard()
                kernel32 = getattr(ctypes, "windll", None).kernel32 if hasattr(ctypes, "windll") else None
                if kernel32:
                    short_path = ctypes.create_unicode_buffer(1024)
                    kernel32.GetShortPathNameW(str(file_path), short_path, 1024)
                    target_path = short_path.value
                else:
                    target_path = str(file_path)
                cmd_open = f'open "{target_path}" type mpegvideo alias {MCI_SB_ALIAS}'
                res = winmm.mciSendStringW(cmd_open, None, 0, 0)
                if res != 0:
                    cmd_open = f'open "{target_path}" alias {MCI_SB_ALIAS}'
                    winmm.mciSendStringW(cmd_open, None, 0, 0)

                winmm.mciSendStringW(f"play {MCI_SB_ALIAS} wait", None, 0, 0)
                _stop_mci_soundboard()
    except Exception as e:
        logger.debug(f"Error in soundboard playback: {e}")
        _stop_mci_soundboard()


@register_tool
def play_soundboard(clip_name: str) -> dict[str, Any]:
    """
    Plays an authentic Aperture Science audio soundboard clip (Cave Johnson lemons rant,
    Wheatley quotes, Space Core, Turret lines, or Neurotoxin alerts) with automatic
    background audio ducking.
    """
    global _current_soundboard_thread
    if not clip_name:
        return {
            "success": False,
            "message": "Please specify a soundboard clip (e.g. 'lemons', 'wheatley', 'space', 'turret', 'neurotoxin').",
        }

    q = clip_name.strip().lower()
    matched_key = None
    if "lemon" in q:
        matched_key = "lemons"
    elif "moron" in q or "punch" in q:
        matched_key = "wheatley_moron"
    elif "wheatley" in q or "hello" in q:
        matched_key = "wheatley_hello"
    elif "space" in q:
        matched_key = "space"
    elif "neurotoxin" in q or "gas" in q:
        matched_key = "neurotoxin"
    elif "turret" in q or "sorry" in q or "blame" in q:
        matched_key = "turret_sorry"
    else:
        for k in SOUNDBOARD_ENTRIES:
            if k in q:
                matched_key = k
                break

    if not matched_key:
        available = ", ".join(SOUNDBOARD_ENTRIES.keys())
        return {
            "success": False,
            "message": f"Soundboard clip '{clip_name}' not found. Available clips: {available}.",
        }

    entry = SOUNDBOARD_ENTRIES[matched_key]
    clip_file = SOUNDBOARD_DIR / f"{matched_key}.mp3"

    if not clip_file.exists() or clip_file.stat().st_size == 0:
        logger.info(f"Synthesizing soundboard asset for '{matched_key}'...")
        _synthesize_soundboard_clip(matched_key, clip_file)

    if not clip_file.exists():
        return {"success": False, "message": f"Failed to prepare audio for {entry['title']}."}

    # Play asynchronously
    _current_soundboard_thread = threading.Thread(
        target=_play_file_with_ducking,
        args=(clip_file,),
        daemon=True,
        name="ApertureSoundboardThread",
    )
    _current_soundboard_thread.start()

    card = (
        "+====================================================================+\n"
        "|   APERTURE SCIENCE ACOUSTIC SYNTHESIZER - SOUNDBOARD BROADCAST     |\n"
        f"| [▶ BROADCASTING] Speaker: {entry['speaker']:<16} Sound: {entry['title'][:17]:<17} |\n"
        "+====================================================================+\n"
        f"| Character         : {entry['speaker']:<46} |\n"
        f"| Audio Title       : {entry['title']:<46} |\n"
        f"| Subsystem Status  : Background Audio Ducked to 15%                 |\n"
        "+--------------------------------------------------------------------+\n"
    )

    return {
        "success": True,
        "clip": matched_key,
        "speaker": entry["speaker"],
        "title": entry["title"],
        "terminal_card": card,
        "message": f"Broadcasting '{entry['title']}' ({entry['speaker']}).",
    }


@register_tool
def stop_soundboard() -> str:
    """Stops any currently playing soundboard audio broadcast."""
    _stop_mci_soundboard()
    return "Aperture soundboard broadcast terminated."
