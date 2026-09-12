"""Speech-to-Text microphone listener with dynamic silence detection."""

import logging
import time
from typing import Callable

import numpy as np
import sounddevice as sd
import speech_recognition as sr

from config import config

logger = logging.getLogger("local_os_agent.voice.listener")


class VoiceListener:
    """
    Microphone audio listener utilizing sounddevice for capture and
    speech_recognition for transcribing natural language commands.
    """

    def __init__(
        self,
        sample_rate: int = 16000,
        energy_threshold: int = 400,
        silence_limit: float = 1.2,
        language: str | None = None,
    ):
        self.sample_rate = sample_rate
        self.energy_threshold = energy_threshold
        self.silence_limit = silence_limit
        self.language = language or config.stt_language
        self.recognizer = sr.Recognizer()

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

        # Combine all audio chunks into a single byte stream
        full_audio = np.concatenate(buffer).tobytes()
        audio_data = sr.AudioData(full_audio, self.sample_rate, 2)

        try:
            text = self.recognizer.recognize_google(audio_data, language=self.language)
            logger.info(f"Transcribed voice command: '{text}'")
            return text
        except sr.UnknownValueError:
            logger.debug("Speech recognition could not understand audio.")
            return None
        except sr.RequestError as re:
            logger.warning(f"Speech recognition service request error: {re}")
            return None
        except Exception as e:
            logger.error(f"Transcription error: {e}")
            return None
