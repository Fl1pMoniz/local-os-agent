"""Unit tests for the 6 multifaceted GLaDOS protocols."""

import unittest
from unittest.mock import MagicMock, patch
import pathlib

from agent import OSAgent
from schemas import AgentResponse, ToolAction
from tools.game_clipper import capture_game_clip, list_recent_clips, format_clip_card
from tools.jellyfin import search_and_play_jellyfin, get_jellyfin_now_playing, format_now_playing_card
from tools.vision import analyze_screen, format_vision_card
from tools.soundboard import play_soundboard, stop_soundboard
from tools.audio_ducking import toggle_audio_ducking, is_ducking_enabled
from tools.subject_wellness import check_subject_status, log_water_intake, format_wellness_card


class TestMultifacetedProtocols(unittest.TestCase):

    def setUp(self):
        self.agent = OSAgent(base_url="http://mock-llm:11434/v1", model="mock-glados")

    # 1. Protocol 2: Replay Capture / 30-Second Clipper
    @patch("tools.game_clipper.user32")
    @patch("tools.game_clipper._is_obs_running", return_value=False)
    @patch("tools.game_clipper._get_active_window_title", return_value="Portal 2")
    def test_capture_game_clip(self, mock_title, mock_obs, mock_u32):
        res = capture_game_clip(seconds=30)
        self.assertTrue(res["success"])
        self.assertEqual(res["seconds"], 30)
        self.assertEqual(res["active_game"], "Portal 2")
        self.assertIn("terminal_card", res)
        self.assertIn("APERTURE SCIENCE REPLAY ARCHIVE", res["terminal_card"])

    def test_format_clip_card(self):
        card = format_clip_card("Cyberpunk 2077", "C:\\Videos\\test.mp4", 15.5, "30s")
        self.assertIn("Cyberpunk 2077", card)
        self.assertIn("15.5 MB", card)
        self.assertIn("30s", card)

    def test_list_recent_clips(self):
        res = list_recent_clips(limit=3)
        self.assertIn("count", res)
        self.assertIn("terminal_card", res)
        self.assertIn("APERTURE SCIENCE RECORDED HIGHLIGHT ARCHIVES", res["terminal_card"])

    # 2. Protocol 1: Jellyfin Media Dispatcher
    @patch("tools.jellyfin.authenticate_jellyfin", return_value="mock-token")
    @patch("tools.jellyfin.requests.get")
    @patch("webbrowser.open")
    def test_search_and_play_jellyfin(self, mock_browser, mock_get, mock_auth):
        mock_get.return_value.status_code = 200
        mock_get.return_value.json.return_value = {"Items": [{"Id": "item-123", "Name": "Inception", "Type": "Movie"}]}
        res = search_and_play_jellyfin("Inception")
        self.assertTrue(res["success"])
        self.assertEqual(res["query"], "Inception")
        self.assertIn("url", res)
        self.assertIn("terminal_card", res)
        self.assertIn("APERTURE SCIENCE MEDIA DISPATCHER", res["terminal_card"])
        mock_browser.assert_called_once()

    @patch("tools.jellyfin.authenticate_jellyfin", return_value="mock-token")
    @patch("tools.jellyfin.requests.get")
    def test_get_jellyfin_now_playing_idle(self, mock_get, mock_auth):
        mock_get.return_value.status_code = 200
        mock_get.return_value.json.return_value = []
        res = get_jellyfin_now_playing()
        self.assertIn("terminal_card", res)
        self.assertIn("APERTURE SCIENCE MEDIA DISPATCHER", res["terminal_card"])

    def test_format_now_playing_card(self):
        card = format_now_playing_card("Dune Part Two", "Movie", "fl1pmoniz", "Playing", "01:12:00 / 02:46:00")
        self.assertIn("Dune Part Two", card)
        self.assertIn("fl1pmoniz", card)

    # 3. Protocol 3: Optical Screen Vision
    @patch("tools.vision._get_active_window_title", return_value="VS Code - main.py")
    @patch("tools.vision.capture_screen_image", return_value=(None, "base64placeholder"))
    def test_analyze_screen(self, mock_capture, mock_title):
        res = analyze_screen("What is this compiler error?")
        self.assertTrue(res["success"])
        self.assertEqual(res["active_window"], "VS Code - main.py")
        self.assertIn("diagnosis", res)
        self.assertIn("terminal_card", res)
        self.assertIn("APERTURE SCIENCE OPTICAL SENSOR", res["terminal_card"])

    def test_format_vision_card(self):
        card = format_vision_card("Terminal", "Error Scan", "Syntax error at line 42", "99.9%")
        self.assertIn("Terminal", card)
        self.assertIn("Syntax error at line 42", card)

    # 4. Protocol 4: Soundboard & Audio Ducking
    def test_toggle_audio_ducking(self):
        current = is_ducking_enabled()
        res = toggle_audio_ducking()
        self.assertEqual(res["enabled"], not current)
        toggle_audio_ducking(True)
        self.assertTrue(is_ducking_enabled())

    @patch("tools.soundboard._synthesize_soundboard_clip", return_value=True)
    @patch("pathlib.Path.exists", return_value=True)
    @patch("threading.Thread")
    def test_play_soundboard(self, mock_thread, mock_exists, mock_synth):
        res = play_soundboard("lemons")
        self.assertTrue(res["success"])
        self.assertEqual(res["speaker"], "Cave Johnson")
        self.assertIn("Combustible Lemons", res["title"])
        self.assertIn("terminal_card", res)

    def test_stop_soundboard(self):
        msg = stop_soundboard()
        self.assertIn("terminated", msg.lower())

    # 5. Protocol 7: Subject Maintenance & Ergonomics
    def test_subject_wellness(self):
        res = check_subject_status()
        self.assertTrue(res["success"])
        self.assertIn("terminal_card", res)
        self.assertIn("APERTURE SCIENCE SUBJECT BIOMETRIC", res["terminal_card"])

    def test_log_water_intake(self):
        res = log_water_intake(250)
        self.assertTrue(res["success"])
        self.assertGreaterEqual(res["total_water_ml"], 250)

    # 6. Intent matching in agent.py
    @patch("openai.OpenAI")
    def test_clip_intent_matching(self, mock_openai_cls):
        mock_client = MagicMock()
        mock_client.chat.completions.create.side_effect = Exception("Offline fallback test")
        self.agent.client = mock_client

        plan = self.agent.query_llm("GLaDOS, clip that")
        self.assertTrue(any(a.tool == "capture_game_clip" for a in plan.actions))

        plan_recent = self.agent.query_llm("show my recent clips")
        self.assertTrue(any(a.tool == "list_recent_clips" for a in plan_recent.actions))

    @patch("openai.OpenAI")
    def test_jellyfin_intent_matching(self, mock_openai_cls):
        mock_client = MagicMock()
        mock_client.chat.completions.create.side_effect = Exception("Offline fallback test")
        self.agent.client = mock_client

        plan = self.agent.query_llm("play Interstellar on Jellyfin")
        self.assertTrue(any(a.tool == "search_and_play_jellyfin" for a in plan.actions))

        plan_status = self.agent.query_llm("what is playing on Jellyfin")
        self.assertTrue(any(a.tool == "get_jellyfin_now_playing" for a in plan_status.actions))

    @patch("openai.OpenAI")
    def test_vision_intent_matching(self, mock_openai_cls):
        mock_client = MagicMock()
        mock_client.chat.completions.create.side_effect = Exception("Offline fallback test")
        self.agent.client = mock_client

        plan = self.agent.query_llm("GLaDOS, inspect this error on my screen")
        self.assertTrue(any(a.tool == "analyze_screen" for a in plan.actions))

    @patch("openai.OpenAI")
    def test_soundboard_intent_matching(self, mock_openai_cls):
        mock_client = MagicMock()
        mock_client.chat.completions.create.side_effect = Exception("Offline fallback test")
        self.agent.client = mock_client

        # Explicit requests to play voicelines MUST match
        plan = self.agent.query_llm("play combustible lemons")
        self.assertTrue(any(a.tool == "play_soundboard" for a in plan.actions))

        plan_cj = self.agent.query_llm("play a cave johnson voiceline")
        self.assertTrue(any(a.tool == "play_soundboard" for a in plan_cj.actions))

        plan_wh = self.agent.query_llm("play wheatley voiceline")
        self.assertTrue(any(a.tool == "play_soundboard" for a in plan_wh.actions))

        # Conversational questions ABOUT Cave Johnson or Wheatley MUST NOT trigger soundboard
        plan_who_cj = self.agent.query_llm("who is cave johnson?")
        self.assertFalse(any(a.tool == "play_soundboard" for a in plan_who_cj.actions))

        plan_tell_cj = self.agent.query_llm("tell me about cave johnson")
        self.assertFalse(any(a.tool == "play_soundboard" for a in plan_tell_cj.actions))

        plan_who_wh = self.agent.query_llm("what is wheatley?")
        self.assertFalse(any(a.tool == "play_soundboard" for a in plan_who_wh.actions))

    @patch("openai.OpenAI")
    def test_wellness_intent_matching(self, mock_openai_cls):
        mock_client = MagicMock()
        mock_client.chat.completions.create.side_effect = Exception("Offline fallback test")
        self.agent.client = mock_client

        plan_status = self.agent.query_llm("check subject status")
        self.assertTrue(any(a.tool == "check_subject_status" for a in plan_status.actions))

        plan_water = self.agent.query_llm("I drank water")
        self.assertTrue(any(a.tool == "log_water_intake" for a in plan_water.actions))


if __name__ == "__main__":
    unittest.main()

