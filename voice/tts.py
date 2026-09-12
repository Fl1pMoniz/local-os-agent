"""Text-to-Speech synthesis with elegant British female neural voice."""

import asyncio
import ctypes
import logging
import os
import queue
import re
import threading
import time
import uuid
from pathlib import Path
from typing import Any

from config import config

logger = logging.getLogger("local_os_agent.voice.tts")


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


class TextToSpeech:
    """
    High-fidelity Text-to-Speech engine utilizing Microsoft Edge's Neural TTS
    ('en-GB-SoniaNeural') with seamless native Windows MCI playback and
    offline SAPI5 fallback.
    """

    def __init__(self, voice: str | None = None, rate: str | None = None):
        self.voice = voice or config.tts_voice
        self.rate = rate or config.tts_rate
        self.cache_dir = config.audio_cache_dir
        self.cache_dir.mkdir(parents=True, exist_ok=True)

        self._speech_queue: queue.Queue[tuple[str, threading.Event | None]] = queue.Queue()
        self._stop_event = threading.Event()
        self._current_alias: str | None = None
        self._lock = threading.Lock()

        # Start background speech processing thread
        self._worker_thread = threading.Thread(target=self._speech_worker, daemon=True)
        self._worker_thread.start()

    def _play_mp3_native(self, file_path: Path) -> None:
        """Plays an audio file using Windows Multimedia API (winmm.dll) without GUI windows."""
        alias = f"tts_{uuid.uuid4().hex[:8]}"
        with self._lock:
            self._current_alias = alias

        winmm = ctypes.windll.winmm
        abs_path = str(file_path.resolve())

        try:
            # Open media device
            open_cmd = f'open "{abs_path}" type mpegvideo alias {alias}'
            err = winmm.mciSendStringW(open_cmd, None, 0, 0)
            if err != 0:
                logger.warning(f"MCI open failed with code {err}")
                return

            # Play file
            play_cmd = f"play {alias} wait"
            winmm.mciSendStringW(play_cmd, None, 0, 0)
        finally:
            winmm.mciSendStringW(f"close {alias}", None, 0, 0)
            with self._lock:
                if self._current_alias == alias:
                    self._current_alias = None

    async def _synthesize_edge(self, text: str, output_path: Path) -> None:
        """Synthesizes text to an MP3 file using edge-tts."""
        import edge_tts
        communicate = edge_tts.Communicate(text, voice=self.voice, rate=self.rate)
        await communicate.save(str(output_path))

    def _speak_offline_sapi(self, text: str) -> None:
        """Offline fallback using Windows native SAPI.SpVoice with a female voice if available."""
        try:
            import comtypes.client
            ctypes.windll.ole32.CoInitialize(None)
            speaker = comtypes.client.CreateObject("SAPI.SpVoice")

            # Try to pick a female voice (Zira or British voice if present)
            voices = speaker.GetVoices()
            for i in range(voices.Count):
                v = voices.Item(i)
                desc = v.GetDescription().lower()
                if "zira" in desc or "hazel" in desc or "female" in desc or "great britain" in desc:
                    speaker.Voice = v
                    break

            speaker.Speak(text, 0)  # Synchronous within the background worker thread
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
            if not text:
                if done_event:
                    done_event.set()
                self._speech_queue.task_done()
                continue

            cleaned = clean_text_for_speech(text)
            if not cleaned:
                if done_event:
                    done_event.set()
                self._speech_queue.task_done()
                continue

            audio_file = self.cache_dir / f"speech_{uuid.uuid4().hex[:8]}.mp3"

            try:
                # 1. Try High-Quality British Neural Voice via edge-tts
                asyncio.run(self._synthesize_edge(cleaned, audio_file))
                self._play_mp3_native(audio_file)
            except Exception as e:
                logger.warning(f"Edge TTS failed ({e}); falling back to offline SAPI5 voice.")
                # 2. Offline SAPI fallback
                self._speak_offline_sapi(cleaned)
            finally:
                # Clean up cached audio file
                try:
                    if audio_file.exists():
                        audio_file.unlink()
                except OSError:
                    pass

                if done_event:
                    done_event.set()
                self._speech_queue.task_done()

    def speak(self, text: str, wait: bool = False) -> None:
        """
        Speaks the given text out loud.
        If wait is True, blocks until the speech finishes.
        If wait is False (default), speaks asynchronously in the background.
        """
        if not config.enable_tts or not text.strip():
            return

        done_event = threading.Event() if wait else None
        self._speech_queue.put((text, done_event))

        if wait and done_event:
            done_event.wait()

    def stop(self) -> None:
        """Stops current audio playback and clears pending speech queue."""
        with self._lock:
            if self._current_alias:
                ctypes.windll.winmm.mciSendStringW(f"stop {self._current_alias}", None, 0, 0)
                ctypes.windll.winmm.mciSendStringW(f"close {self._current_alias}", None, 0, 0)
                self._current_alias = None

        # Empty the queue
        while not self._speech_queue.empty():
            try:
                _, done_event = self._speech_queue.get_nowait()
                if done_event:
                    done_event.set()
                self._speech_queue.task_done()
            except queue.Empty:
                break


# Global singleton TTS engine
tts_engine = TextToSpeech()

