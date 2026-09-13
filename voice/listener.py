"""Speech-to-Text microphone listener with dynamic silence detection."""

import logging
import time
from typing import Callable

import numpy as np
import sounddevice as sd
import speech_recognition as sr

from config import config

logger = logging.getLogger("local_os_agent.voice.listener")


def extract_wake_word_command(text: str, wake_word: str | None = None) -> tuple[bool, str]:
    """
    Checks if the specified wake word (e.g. 'cortana' or 'hey cortana') is present in the text.
    Returns (is_called, extracted_command).
    """
    if not text:
        return False, ""

    target_word = (wake_word or config.wake_word).strip().lower()
    text_clean = text.lower().strip()

    variations = [
        f"hey {target_word}",
        f"ok {target_word}",
        f"hi {target_word}",
        target_word,
    ]

    for variant in variations:
        if variant in text_clean:
            # Strip the wake variant while preserving original text casing
            idx = text_clean.find(variant)
            before = text[:idx].strip()
            after = text[idx + len(variant):].strip()
            command = f"{before} {after}".strip().strip(",.?! ")
            return True, command

    return False, ""


class VoiceListener:
    """
    Microphone audio listener utilizing sounddevice for high-fidelity capture and
    OpenAI Whisper (https://github.com/openai/whisper) for local neural Speech-to-Text.
    """

    def __init__(
        self,
        sample_rate: int = 16000,
        energy_threshold: int = 400,
        silence_limit: float = 1.2,
        language: str | None = None,
        whisper_model: str | None = None,
        whisper_device: str | None = None,
    ):
        self.sample_rate = sample_rate
        self.energy_threshold = energy_threshold
        self.silence_limit = silence_limit
        self.language = language or config.stt_language
        self.whisper_model_name = whisper_model or config.whisper_model
        self.whisper_device = whisper_device or config.whisper_device
        self.vram_limit_mb = config.whisper_vram_limit_mb
        self._fp16 = False

        self._whisper_model = None
        self._load_whisper()
        self.recognizer = sr.Recognizer()

    def _load_whisper(self) -> None:
        """Loads OpenAI Whisper model locally for private offline transcription."""
        if config.stt_engine.lower() == "google":
            logger.info("STT configured to Google SpeechRecognition.")
            return

        try:
            import whisper
            import torch

            target_device = self.whisper_device
            if target_device.startswith("cuda"):
                if torch.cuda.is_available():
                    # Strictly limit GPU VRAM usage to <= 1GB (1024 MB)
                    try:
                        total_mem = torch.cuda.get_device_properties(0).total_memory
                        max_allowed_bytes = min(self.vram_limit_mb * 1024 * 1024, 1024 * 1024 * 1024)
                        fraction = max_allowed_bytes / total_mem
                        torch.cuda.set_per_process_memory_fraction(fraction, 0)
                        logger.info(
                            f"Enforced Whisper GPU VRAM budget: {self.vram_limit_mb} MB "
                            f"({fraction * 100:.2f}% of {total_mem / (1024**3):.1f} GB total VRAM)"
                        )
                    except Exception as mem_err:
                        logger.warning(f"Could not set CUDA memory fraction: {mem_err}")
                    self._fp16 = True
                else:
                    logger.warning("CUDA requested for Whisper but not available; falling back to CPU.")
                    target_device = "cpu"
                    self._fp16 = False
            else:
                self._fp16 = False

            logger.info(f"Loading OpenAI Whisper ('{self.whisper_model_name}') on {target_device} (fp16={self._fp16})...")
            self._whisper_model = whisper.load_model(self.whisper_model_name, device=target_device)
            self.whisper_device = target_device
            logger.info("OpenAI Whisper model loaded successfully.")
        except Exception as e:
            logger.warning(f"Failed to load OpenAI Whisper ({e}); falling back to Google SpeechRecognition.")
            self._whisper_model = None

    def calibrate_ambient_noise(self, duration: float = 1.0) -> int:
        """Measures background ambient noise level to calibrate dynamic threshold."""
        try:
            samples = int(duration * self.sample_rate)
            recording = sd.rec(samples, samplerate=self.sample_rate, channels=1, dtype="int16")
            sd.wait()
            data = recording.flatten()
            rms = int(np.sqrt(np.mean(data.astype(np.float64) ** 2)))
            # Set threshold slightly above ambient noise
            self.energy_threshold = max(350, int(rms * 1.5))
            logger.debug(f"Ambient noise RMS: {rms}, calibrated threshold: {self.energy_threshold}")
            return self.energy_threshold
        except Exception as e:
            logger.warning(f"Could not calibrate ambient noise: {e}")
            return self.energy_threshold

    def listen_command(
        self,
        max_duration: float = 12.0,
        timeout: float = 6.0,
        on_listening: Callable[[], None] | None = None,
        on_speech_detected: Callable[[], None] | None = None,
    ) -> str | None:
        """
        Listens for a spoken voice command via the microphone.
        Automatically starts buffering when user speaks and stops after detecting silence.
        Returns the transcribed text, or None if no speech was detected.
        """
        chunk_duration = 0.1  # 100ms chunks
        chunk_size = int(self.sample_rate * chunk_duration)

        buffer: list[np.ndarray] = []
        is_speaking = False
        silence_start: float | None = None
        listen_start = time.time()

        if on_listening:
            on_listening()

        try:
            with sd.InputStream(samplerate=self.sample_rate, channels=1, dtype="int16") as stream:
                while True:
                    elapsed = time.time() - listen_start

                    # Check overall timeout before any speech is detected
                    if not is_speaking and elapsed > timeout:
                        logger.debug("Voice listening timed out (no speech detected).")
                        return None

                    # Check max recording length limit
                    if is_speaking and elapsed > max_duration:
                        logger.debug("Max recording duration reached.")
                        break

                    chunk, overflowed = stream.read(chunk_size)
                    chunk_flat = chunk.flatten()
                    rms = int(np.sqrt(np.mean(chunk_flat.astype(np.float64) ** 2)))

                    if rms > self.energy_threshold:
                        if not is_speaking:
                            is_speaking = True
                            if on_speech_detected:
                                on_speech_detected()
                        silence_start = None
                        buffer.append(chunk_flat)
                    else:
                        if is_speaking:
                            buffer.append(chunk_flat)
                            if silence_start is None:
                                silence_start = time.time()
                            elif (time.time() - silence_start) >= self.silence_limit:
                                # User stopped speaking
                                logger.debug("Silence detected after speech; processing.")
                                break

        except Exception as e:
            logger.exception(f"Audio stream error: {e}")
            return None

        if not buffer or not is_speaking:
            return None

        # Combine all audio chunks into int16 array
        audio_int16 = np.concatenate(buffer)

        # 1. Primary Engine: OpenAI Whisper (https://github.com/openai/whisper)
        if self._whisper_model is not None:
            try:
                audio_float32 = audio_int16.astype(np.float32) / 32768.0
                result = self._whisper_model.transcribe(
                    audio_float32,
                    language=self.language,
                    fp16=self._fp16,
                    verbose=False,
                )
                if self.whisper_device.startswith("cuda"):
                    import torch
                    torch.cuda.empty_cache()

                text = (result.get("text") or "").strip().strip("\"'")
                if text:
                    logger.info(f"Transcribed voice command (OpenAI Whisper on {self.whisper_device}): '{text}'")
                    return text
                return None
            except Exception as e:
                logger.warning(f"OpenAI Whisper transcription error: {e}; trying SpeechRecognition fallback.")

        # 2. Fallback Engine: SpeechRecognition (Google Web Speech API)
        try:
            full_audio = audio_int16.tobytes()
            audio_data = sr.AudioData(full_audio, self.sample_rate, 2)
            text = self.recognizer.recognize_google(audio_data, language=self.language)
            logger.info(f"Transcribed voice command (Google STT fallback): '{text}'")
            return text
        except sr.UnknownValueError:
            logger.debug("Speech recognition could not understand audio.")
            return None
        except Exception as e:
            logger.error(f"Transcription error: {e}")
            return None

