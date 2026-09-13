"""Unit tests for GLaDOS expanded toolset and intent routing."""

import unittest
from unittest.mock import patch, MagicMock

from tools.companion import get_active_window, roast_user, get_active_window_info
from tools.sfx import get_sfx_path, play_portal_sfx, stop_sfx, VPK_SFX_MAP
from tools.web import open_website, get_weather, wikipedia_lookup, KNOWN_URL_ALIASES
from tools.system import get_system_stats, set_timer, get_clipboard, set_clipboard
from agent import OSAgent, extract_json_payload


class TestExpandedTools(unittest.TestCase):

    def test_known_website_aliases(self):
        self.assertIn("youtube", KNOWN_URL_ALIASES)
        self.assertIn("github", KNOWN_URL_ALIASES)
        self.assertIn("portal wiki", KNOWN_URL_ALIASES)

    @patch("webbrowser.open")
    def test_open_website(self, mock_open):
        mock_open.return_value = True
        success, msg = open_website("youtube")
        self.assertTrue(success)
        mock_open.assert_called_with("https://www.youtube.com")

        success2, msg2 = open_website("quantum computing")
        self.assertTrue(success2)
        self.assertIn("google.com/search", msg2)

    def test_active_window_and_roast(self):
        success, win_info = get_active_window()
        self.assertTrue(success)
        self.assertIn("Active Window:", win_info)

        success_roast, roast = roast_user()
        self.assertTrue(success_roast)
        self.assertIsInstance(roast, str)
        self.assertGreater(len(roast), 10)

    def test_sfx_resolution_and_maps(self):
        self.assertIn("radio", VPK_SFX_MAP)
        self.assertIn("turret_hello", VPK_SFX_MAP)
        # Verify get_sfx_path returns a Path or None without crashing
        path = get_sfx_path("radio")
        # stop_sfx should succeed safely
        stop_success, stop_msg = stop_sfx()
        self.assertTrue(stop_success)

    def test_system_stats_gpu_telemetry(self):
        success, stats = get_system_stats()
        self.assertTrue(success)
        self.assertIn("cpu", stats)
        self.assertIn("ram", stats)
        self.assertIn("battery", stats)
        self.assertIn("gpu", stats)
        if stats["gpu"] is not None:
            self.assertIn("device", stats["gpu"])
            self.assertIn("allocated_mb", stats["gpu"])

    def test_clipboard_operations(self):
        test_string = "Aperture Science Portal Gun Protocol 99"
        set_ok, set_msg = set_clipboard(test_string)
        self.assertTrue(set_ok)

        get_ok, content = get_clipboard()
        self.assertTrue(get_ok)
        self.assertEqual(content, test_string)

    def test_set_timer_validation(self):
        success, msg = set_timer(10, label="Cake baking")
        self.assertTrue(success)
        self.assertIn("10 seconds", msg)

        fail_success, fail_msg = set_timer(-5)
        self.assertFalse(fail_success)


class TestAgentDeterministicIntents(unittest.TestCase):

    @patch("openai.resources.chat.completions.Completions.create")
    def test_intent_intercepts(self, mock_create):
        # Configure mock LLM response with default conversational reply
        mock_response = MagicMock()
        mock_response.choices = [
            MagicMock(message=MagicMock(content='{"thought": "Processing", "response": "Yes, test subject?", "actions": []}'))
        ]
        mock_create.return_value = mock_response

        agent = OSAgent(enable_voice=False)

        # Test roast intent
        plan = agent.query_llm("GLaDOS roast me please")
        self.assertTrue(any(a.tool == "roast_user" for a in plan.actions))

        # Test portal radio intent
        plan = agent.query_llm("GLaDOS play the portal radio")
        self.assertTrue(any(a.tool == "play_portal_sfx" and a.args.get("effect_name") == "radio" for a in plan.actions))

        # Test stop radio
        plan = agent.query_llm("GLaDOS stop radio now")
        self.assertTrue(any(a.tool == "stop_sfx" for a in plan.actions))

        # Test lock PC intent
        plan = agent.query_llm("GLaDOS lock my pc")
        self.assertTrue(any(a.tool == "lock_workstation" for a in plan.actions))

        # Test read clipboard intent
        plan = agent.query_llm("GLaDOS read clipboard aloud")
        self.assertTrue(any(a.tool == "read_clipboard_aloud" for a in plan.actions))


if __name__ == "__main__":
    unittest.main()
