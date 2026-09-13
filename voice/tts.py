"""Text-to-Speech synthesis with authentic local GLaDOS neural voice (Piper/VITS) and Edge TTS fallback."""

import asyncio
import ctypes
import logging
import os
import queue
import re
import threading
import time
import urllib.request
import uuid
import wave
from pathlib import Path
from typing import Any

from config import config
from voice.audio_arbiter import GLOBAL_AUDIO_LOCK

logger = logging.getLogger("local_os_agent.voice.tts")

# Path to the local GLaDOS Piper ONNX neural voice model
MODELS_DIR = Path(__file__).resolve().parent / "models" / "glados"
PIPER_MODEL_PATH = MODELS_DIR / "glados.onnx"
PIPER_CONFIG_PATH = MODELS_DIR / "glados.onnx.json"
HF_MODEL_URL = "https://huggingface.co/rokeya71/VITS-Piper-GlaDOS-en-onnx/resolve/main/"


def clean_text_for_speech(text: str) -> str:
    """Cleans up markdown, links, and code symbols for natural human-like speech."""
    if not text:
        return ""

    # Remove markdown code blocks and inline backticks
    cleaned = re.sub(r"```[\s\S]*?```", "", text)
    cleaned = re.sub(r"`([^`]+)`", r"\1", cleaned)

    # Remove URLs
    cleaned = re.sub(r"https?://\S+", "", cleaned)

    # Remove markdown bold/italics
    cleaned = re.sub(r"[*_]{1,3}([^*_]+)[*_]{1,3}", r"\1", cleaned)

    # Remove emojis and special formatting characters
    cleaned = re.sub(r"[\U00010000-\U0010ffff]", "", cleaned)
    cleaned = re.sub(r"[#>\-\[\]\(\)]", " ", cleaned)

    # Normalize whitespace
    cleaned = re.sub(r"\s+", " ", cleaned).strip()
    return cleaned


VOICE_PRESETS: dict[str, dict[str, str]] = {
    "glados": {
        "voice": "glados_piper",
        "pitch": "+0Hz",
        "rate": "+0%",
        "desc": "Authentic Aperture Science GLaDOS neural voice (local Piper VITS model trained on Portal game files)",
    },
    "glados_edge": {
        "voice": "en-US-AvaMultilingualNeural",
        "pitch": "+4Hz",
        "rate": "-4%",
        "desc": "Portal 2 GLaDOS via Edge-TTS (Ellen McLain emulation: calm, measured & deadpan)",
    },
    "glados_jenny": {
        "voice": "en-US-JennyNeural",
        "pitch": "+3Hz",
        "rate": "-5%",
        "desc": "Crisp American synthetic GLaDOS variant",
    },
    "glados_robot": {
        "voice": "en-US-AnaNeural",
        "pitch": "-6Hz",
        "rate": "-4%",
        "desc": "High-synthetic deeper robotic GLaDOS variant",
    },
    "libby": {
        "voice": "en-GB-LibbyNeural",
        "pitch": "+2Hz",
        "rate": "+2%",
        "desc": "Crisp, elegant & articulate British female",
    },
    "aria": {
        "voice": "en-US-AriaNeural",
        "pitch": "+0Hz",
        "rate": "+2%",
        "desc": "The iconic Microsoft Cortana / Copilot expressive AI assistant voice",
    },
}


class TextToSpeech:
    """
    High-fidelity Text-to-Speech engine utilizing:
    1. Authentic local GLaDOS neural voice via Piper (ONNX VITS trained on Portal assets).
    2. Cloud Microsoft Edge Neural TTS with SSML pacing.
    3. Offline Windows SAPI5 voice fallback.
    """

    def __init__(self, voice: str | None = None, rate: str | None = None, pitch: str | None = None):
        raw_voice = (voice or config.tts_voice).lower()
        if raw_voice in VOICE_PRESETS:
            preset = VOICE_PRESETS[raw_voice]
            self.preset_key = raw_voice
            self.voice = preset["voice"]
            self.pitch = pitch or preset["pitch"]
            self.rate = rate or preset["rate"]
        else:
            self.preset_key = raw_voice
            self.voice = voice or config.tts_voice
            self.pitch = pitch or config.tts_pitch
            self.rate = rate or config.tts_rate

        self.cache_dir = config.audio_cache_dir
        self.cache_dir.mkdir(parents=True, exist_ok=True)

        self._piper_voice: Any = None
        self._piper_loaded: bool = False
        self._init_piper()

        self._speech_queue: queue.Queue[tuple[str, threading.Event | None]] = queue.Queue()
        self._stop_event = threading.Event()
        self._cancel_event = threading.Event()
        self._current_alias: str | None = None
        self._lock = threading.Lock()

        # Start background speech processing thread
        self._worker_thread = threading.Thread(target=self._speech_worker, daemon=True)
        self._worker_thread.start()

    def _ensure_piper_model(self) -> bool:
        """Ensures the GLaDOS ONNX model and config are downloaded locally."""
        try:
            MODELS_DIR.mkdir(parents=True, exist_ok=True)
            if not PIPER_CONFIG_PATH.exists():
                logger.info("Downloading GLaDOS voice config (glados.onnx.json)...")
                urllib.request.urlretrieve(HF_MODEL_URL + "glados.onnx.json", PIPER_CONFIG_PATH)
            if not PIPER_MODEL_PATH.exists():
                logger.info("Downloading GLaDOS voice weights (glados.onnx)...")
                urllib.request.urlretrieve(HF_MODEL_URL + "glados.onnx", PIPER_MODEL_PATH)
            return PIPER_MODEL_PATH.exists() and PIPER_CONFIG_PATH.exists()
        except Exception as e:
            logger.warning(f"Could not download GLaDOS Piper model: {e}")
            return False

    def _init_piper(self) -> None:
        """Initializes the Piper neural voice engine for authentic GLaDOS voice."""
        try:
            import piper

            if not PIPER_MODEL_PATH.exists() or not PIPER_CONFIG_PATH.exists():
                if not self._ensure_piper_model():
                    logger.warning("Piper GLaDOS model files missing; will use Edge TTS fallback.")
                    return

            self._piper_voice = piper.PiperVoice.load(
                str(PIPER_MODEL_PATH),
                config_path=str(PIPER_CONFIG_PATH),
            )
            self._piper_loaded = True
            logger.info("Aperture Science GLaDOS neural voice (Piper VITS) loaded successfully.")
        except Exception as e:
            logger.warning(f"Failed to load Piper GLaDOS voice model ({e}); will use Edge TTS.")
            self._piper_loaded = False

    def _play_audio_native(self, file_path: Path) -> None:
        """Plays an audio file (.wav or .mp3) using Windows Multimedia API (winmm.dll) without GUI windows."""
        with GLOBAL_AUDIO_LOCK:
            if self._cancel_event.is_set():
                return

            alias = f"tts_{uuid.uuid4().hex[:8]}"
            with self._lock:
                self._current_alias = alias

            winmm = ctypes.windll.winmm
            abs_path = str(file_path.resolve())
            is_wav = file_path.suffix.lower() == ".wav"
            device_type = "waveaudio" if is_wav else "mpegvideo"

            try:
                # Open media device
                open_cmd = f'open "{abs_path}" type {device_type} alias {alias}'
                err = winmm.mciSendStringW(open_cmd, None, 0, 0)
                if err != 0:
                    logger.warning(f"MCI open failed with code {err}")
                    return

                # Play file synchronously in the background thread with smart audio ducking
                try:
                    from tools.audio_ducking import audio_ducked
                    with audio_ducked(target_fraction=0.20):
                        play_cmd = f"play {alias} wait"
                        winmm.mciSendStringW(play_cmd, None, 0, 0)
                except Exception:
                    play_cmd = f"play {alias} wait"
                    winmm.mciSendStringW(play_cmd, None, 0, 0)
            finally:
                winmm.mciSendStringW(f"close {alias}", None, 0, 0)
                with self._lock:
                    if self._current_alias == alias:
                        self._current_alias = None

    def _synthesize_piper(self, text: str, output_path: Path) -> bool:
        """Synthesizes text directly using local GLaDOS Piper neural voice to WAV."""
        if not self._piper_loaded or self._piper_voice is None:
            return False
        try:
            with wave.open(str(output_path), "wb") as wav_file:
                self._piper_voice.synthesize_wav(text, wav_file)
            return output_path.exists() and output_path.stat().st_size > 0
        except Exception as e:
            logger.warning(f"Piper synthesis error: {e}")
            return False

    def _format_glados_ssml(self, text: str) -> str:
        """Wraps text in SSML with deliberate Aperture pauses between sentences and clauses."""
        import xml.sax.saxutils as saxutils

        escaped = saxutils.escape(text)
        spaced = re.sub(r"([.?!])\s+", r'\1 <break time="250ms"/> ', escaped)
        spaced = re.sub(r"(,)\s+", r'\1 <break time="150ms"/> ', spaced)

        edge_voice = self.voice if self.voice != "glados_piper" else "en-US-AvaMultilingualNeural"
        return (
            f"<speak version='1.0' xmlns='http://www.w3.org/2001/10/synthesis' xml:lang='en-US'>"
            f"<voice name='{edge_voice}'>"
            f"<prosody pitch='{self.pitch}' rate='{self.rate}'>"
            f"{spaced}"
            f"</prosody></voice></speak>"
        )

    async def _synthesize_edge(self, text: str, output_path: Path) -> None:
        """Synthesizes text to an MP3 file using edge-tts with dynamic pitch, rate, and deliberate pacing."""
        import edge_tts

        edge_voice = self.voice if self.voice != "glados_piper" else "en-US-AvaMultilingualNeural"
        try:
            ssml = self._format_glados_ssml(text)
            communicate = edge_tts.Communicate(ssml, voice=edge_voice)
            await communicate.save(str(output_path))
        except Exception as e:
            logger.debug(f"SSML synthesis failed, falling back to standard synthesis: {e}")
            communicate = edge_tts.Communicate(text, voice=edge_voice, rate=self.rate, pitch=self.pitch)
            await communicate.save(str(output_path))

    def _speak_offline_sapi(self, text: str) -> None:
        """Offline fallback using Windows native SAPI.SpVoice with a female voice if available."""
        with GLOBAL_AUDIO_LOCK:
            if self._cancel_event.is_set():
                return
            try:
                import comtypes.client

                ctypes.windll.ole32.CoInitialize(None)
                speaker = comtypes.client.CreateObject("SAPI.SpVoice")

                voices = speaker.GetVoices()
                for i in range(voices.Count):
                    v = voices.Item(i)
                    desc = v.GetDescription().lower()
                    if "zira" in desc or "hazel" in desc or "female" in desc:
                        speaker.Voice = v
                        break

                speaker.Speak(text, 0)
            except Exception as e:
                logger.error(f"SAPI offline speech error: {e}")

    def _speech_worker(self) -> None:
        """Background worker thread that processes and speaks queued messages."""
        while not self._stop_event.is_set():
            try:
                item = self._speech_queue.get(timeout=0.5)
            except queue.Empty:
                continue

            text, done_event = item
            if not text or self._cancel_event.is_set():
                if done_event:
                    done_event.set()
                self._speech_queue.task_done()
                continue

            cleaned = clean_text_for_speech(text)
            if not cleaned or self._cancel_event.is_set():
                if done_event:
                    done_event.set()
                self._speech_queue.task_done()
                continue

            try:
                from ui.state import ui_state
                ui_state.update(state="speaking", text=cleaned)
            except Exception:
                pass

            audio_file = None
            try:
                # 1. Primary Engine: Authentic Piper GLaDOS Neural Voice (if requested or default)
                use_piper = self.voice in ("glados_piper", "glados") or self.preset_key == "glados"
                piper_success = False

                if use_piper and self._piper_loaded and not self._cancel_event.is_set():
                    audio_file = self.cache_dir / f"speech_{uuid.uuid4().hex[:8]}.wav"
                    piper_success = self._synthesize_piper(cleaned, audio_file)
                    if piper_success and not self._cancel_event.is_set():
                        self._play_audio_native(audio_file)

                # 2. Secondary Engine: Microsoft Edge Neural TTS
                if not piper_success and not self._cancel_event.is_set():
                    audio_file = self.cache_dir / f"speech_{uuid.uuid4().hex[:8]}.mp3"
                    asyncio.run(self._synthesize_edge(cleaned, audio_file))
                    if not self._cancel_event.is_set():
                        self._play_audio_native(audio_file)

            except Exception as e:
                if not self._cancel_event.is_set():
                    logger.warning(f"Neural TTS failed ({e}); falling back to offline SAPI5 voice.")
                    self._speak_offline_sapi(cleaned)

            finally:
                # Clean up temporary cached audio file
                if audio_file and audio_file.exists():
                    try:
                        audio_file.unlink()
                    except OSError:
                        pass

                if done_event:
                    done_event.set()
                self._speech_queue.task_done()
                try:
                    from ui.state import ui_state
                    ui_state.update(state="idle")
                except Exception:
                    pass

    def speak(self, text: str, wait: bool = False) -> None:
        """
        Speaks the given text out loud.
        If wait is True, blocks until the speech finishes.
        If wait is False (default), speaks asynchronously in the background.
        """
        if not config.enable_tts or not text.strip():
            return

        self._cancel_event.clear()
        done_event = threading.Event() if wait else None
        self._speech_queue.put((text, done_event))

        if wait and done_event:
            done_event.wait()

    def stop(self) -> None:
        """Stops ongoing speech playback immediately and cancels pending queue items."""
        self._cancel_event.set()
        while not self._speech_queue.empty():
            try:
                _, done_event = self._speech_queue.get_nowait()
                if done_event:
                    done_event.set()
                self._speech_queue.task_done()
            except queue.Empty:
                break

        with self._lock:
            if self._current_alias:
                try:
                    winmm = ctypes.windll.winmm
                    winmm.mciSendStringW(f"stop {self._current_alias}", None, 0, 0)
                    winmm.mciSendStringW(f"close {self._current_alias}", None, 0, 0)
                except Exception:
                    pass
                self._current_alias = None

        # Purge any pending SAPI speech immediately
        try:
            import comtypes.client
            speaker = comtypes.client.CreateObject("SAPI.SpVoice")
            speaker.Speak("", 2)
        except Exception:
            pass

        try:
            from ui.state import ui_state
            ui_state.update(state="idle")
        except Exception:
            pass

    @property
    def is_speaking(self) -> bool:
        """Returns True if GLaDOS is currently speaking or has speech queued."""
        with self._lock:
            return self._current_alias is not None or not self._speech_queue.empty()

    def wait_until_idle(self, timeout: float = 15.0) -> None:
        """Blocks until all queued speech has completed playback."""
        start = time.time()
        while self.is_speaking and (time.time() - start) < timeout:
            time.sleep(0.05)


# Global singleton TTS engine
tts_engine = TextToSpeech()
