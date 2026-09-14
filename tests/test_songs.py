"""Tests for GLaDOS songs ('Still Alive' and 'Want You Gone')."""

import unittest

from tools import execute_tool, get_tool
from tools.songs import get_song_file, is_song_playing, sing_song, stop_song


class TestGLaDOSSongs(unittest.TestCase):
    def test_song_files_exist_or_resolve(self):
        still_alive = get_song_file("still_alive")
        self.assertIsNotNone(still_alive)
        self.assertTrue(still_alive.exists())
        self.assertGreater(still_alive.stat().st_size, 100000)

        want_you_gone = get_song_file("want_you_gone")
        self.assertIsNotNone(want_you_gone)
        self.assertTrue(want_you_gone.exists())
        self.assertGreater(want_you_gone.stat().st_size, 100000)

    def test_song_tool_registration(self):
        sing_def = get_tool("sing_song")
        self.assertIsNotNone(sing_def)
        self.assertIn("song_name", sing_def.signature.parameters)

        stop_def = get_tool("stop_song")
        self.assertIsNotNone(stop_def)

    def test_sing_and_stop_song(self):
        # Stop any active song
        stop_song()
        self.assertFalse(is_song_playing())

        # Start Still Alive
        success, msg = sing_song("still_alive")
        self.assertTrue(success)
        self.assertIn("Still Alive", msg)
        self.assertTrue(is_song_playing())

        # Stop song
        success, msg = stop_song()
        self.assertTrue(success)
        self.assertFalse(is_song_playing())

    def test_execute_tool_dispatch(self):
        res = execute_tool("sing_song", {"song_name": "want_you_gone"})
        self.assertTrue(res.success)
        self.assertEqual(res.status, "success")
        self.assertIn("Want You Gone", res.message)

        # Stop it via execute_tool
        stop_res = execute_tool("stop_song")
        self.assertTrue(stop_res.success)
        self.assertFalse(is_song_playing())


if __name__ == "__main__":
    unittest.main()
