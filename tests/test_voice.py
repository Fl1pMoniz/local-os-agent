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


if __name__ == "__main__":
    unittest.main()
