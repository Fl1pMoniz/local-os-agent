"""Tests for Text-to-Speech synthesis and voice text cleaning."""

import unittest
from pathlib import Path
from voice.tts import TextToSpeech, clean_text_for_speech


class TestVoiceModule(unittest.TestCase):
    def test_clean_text_for_speech(self):
        # Markdown, URLs, and symbols should be stripped
        dirty = "Sure! Here is the link: https://youtube.com/watch?v=123. **Launching** `notepad.exe` now! 🎉"
        cleaned = clean_text_for_speech(dirty)
        self.assertNotIn("https://", cleaned)
        self.assertNotIn("**", cleaned)
        self.assertNotIn("`", cleaned)
        self.assertNotIn("🎉", cleaned)
        self.assertIn("Launching notepad.exe now", cleaned)

    def test_tts_initialization(self):
        tts = TextToSpeech(voice="en-GB-SoniaNeural")
        self.assertEqual(tts.voice, "en-GB-SoniaNeural")
        self.assertTrue(tts.cache_dir.exists())

    def test_clean_text_empty(self):
        self.assertEqual(clean_text_for_speech(""), "")
        self.assertEqual(clean_text_for_speech("   "), "")

    def test_extract_wake_word_command(self):
        from voice import extract_wake_word_command

        # Called with direct command
        called, cmd = extract_wake_word_command("Hey GLaDOS, set volume to 50", wake_word="glados")
        self.assertTrue(called)
        self.assertEqual(cmd, "set volume to 50")

        # Called with just name
        called, cmd = extract_wake_word_command("GLaDOS", wake_word="glados")
        self.assertTrue(called)
        self.assertEqual(cmd, "")

        # Called with question
        called, cmd = extract_wake_word_command("GLaDOS, what is my CPU usage?", wake_word="glados")
        self.assertTrue(called)
        self.assertEqual(cmd, "what is my CPU usage")

        # Ambient speech without GLaDOS
        called, cmd = extract_wake_word_command("Turn up the music please", wake_word="glados")
        self.assertFalse(called)
        self.assertEqual(cmd, "")

    def test_glados_lines(self):
        from voice import GLADOS_VOICELINES, get_contextual_quip, get_glados_quote

        # Quotes exist and are strings
        boot_quote = get_glados_quote("boot")
        self.assertIsInstance(boot_quote, str)
        self.assertIn(boot_quote, GLADOS_VOICELINES["boot"])

        # Contextual quips
        vol_quip = get_contextual_quip("set_volume")
        self.assertIn(vol_quip, GLADOS_VOICELINES["volume"])

        game_quip = get_contextual_quip("launch_steam_game")
        self.assertIn(game_quip, GLADOS_VOICELINES["game_launch"])

        app_quip = get_contextual_quip("launch_app")
        self.assertIn(app_quip, GLADOS_VOICELINES["app_launch"])

        fail_quip = get_contextual_quip("launch_app", success=False)
        self.assertIn("failed", fail_quip.lower())

    def test_whisper_integration(self):
        import torch
        from voice.listener import VoiceListener
        from config import config

        listener = VoiceListener()
        self.assertIsNotNone(listener._whisper_model)
        self.assertEqual(listener.whisper_model_name, config.whisper_model)

        expected_device = "cuda" if torch.cuda.is_available() else "cpu"
        self.assertTrue(listener.whisper_device.startswith(expected_device))
        self.assertLessEqual(listener.vram_limit_mb, 1024)

        if torch.cuda.is_available():
            self.assertTrue(listener._fp16)
            # Verify actual allocated VRAM is <= 1024 MB
            allocated_mb = torch.cuda.memory_allocated() / (1024 * 1024)
            self.assertLess(allocated_mb, 1024)


if __name__ == "__main__":
    unittest.main()

