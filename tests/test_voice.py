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


if __name__ == "__main__":
    unittest.main()

