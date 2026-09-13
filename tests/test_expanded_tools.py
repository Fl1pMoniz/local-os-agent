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

        # Test volume relative up & down
        plan_up = agent.query_llm("GLaDOS volume up please")
        self.assertTrue(any(a.tool == "change_volume_relative" and a.args.get("delta") == 15 for a in plan_up.actions))

        plan_down = agent.query_llm("GLaDOS turn it down")
        self.assertTrue(any(a.tool == "change_volume_relative" and a.args.get("delta") == -15 for a in plan_down.actions))

        plan_exact = agent.query_llm("GLaDOS set volume to 40%")
        self.assertTrue(any(a.tool == "set_volume" and a.args.get("level") == 40 for a in plan_exact.actions))

        # Test YouTube Music vs regular YouTube
        plan_ytm = agent.query_llm("GLaDOS play Radiohead on youtube music")
        self.assertTrue(any(a.tool == "play_youtube" and a.args.get("music") is True for a in plan_ytm.actions))

        plan_yt = agent.query_llm("GLaDOS search portal trailer on youtube")
        self.assertTrue(any(a.tool == "play_youtube" and a.args.get("music") is False for a in plan_yt.actions))

        # Test Flightradar24 tracking intent
        plan_flight = agent.query_llm("GLaDOS track flight AA100")
        self.assertTrue(any(a.tool == "track_flight" and "AA100" in a.args.get("flight_query", "") for a in plan_flight.actions))

        # Test ZimaOS server intent
        plan_zima = agent.query_llm("GLaDOS check my ZimaOS server")
        self.assertTrue(any(a.tool == "get_zimaos_status" for a in plan_zima.actions))

        plan_zima_apps = agent.query_llm("GLaDOS check ZimaOS containers")
        self.assertTrue(any(a.tool == "list_zimaos_apps" for a in plan_zima_apps.actions))

        plan_zima_dash = agent.query_llm("GLaDOS open ZimaOS dashboard")
        self.assertTrue(any(a.tool == "open_zimaos_dashboard" for a in plan_zima_dash.actions))


class TestNewTools(unittest.TestCase):

    @patch("urllib.request.urlopen")
    def test_track_flight_mock(self, mock_urlopen):
        from tools.flight import track_flight

        # Mock FR24 JSON response with type: live
        mock_resp = MagicMock()
        mock_resp.read.return_value = b'{"results": [{"id": "live_123", "type": "live", "label": "AA100 (AAL100)", "detail": {"callsign": "AAL100", "route": "JFK-LHR", "aircraft": "B772", "lat": 40.64, "lon": -73.77}}]}'
        mock_resp.__enter__.return_value = mock_resp
        mock_urlopen.return_value = mock_resp

        success, msg = track_flight("AA100", open_browser=False)
        self.assertTrue(success)
        self.assertIn("AA100", msg)

    @patch("urllib.request.urlopen")
    def test_zimaos_status_mock(self, mock_urlopen):
        from tools.zimaos import get_zimaos_status

        mock_resp = MagicMock()
        mock_resp.read.return_value = b'{"data": {"cpu": {"model_name": "Intel N100", "usage": 12}, "memory": {"total": 8589934592, "used": 2147483648}}}'
        mock_resp.__enter__.return_value = mock_resp
        mock_urlopen.return_value = mock_resp

        success, res = get_zimaos_status()
        self.assertTrue(success)
        self.assertIn("ZimaOS", res)

    @patch("webbrowser.open")
    def test_open_zimaos_dashboard(self, mock_open):
        from tools.zimaos import open_zimaos_dashboard
        mock_open.return_value = True
        success, msg = open_zimaos_dashboard()
        self.assertTrue(success)
        self.assertIn("ZimaOS dashboard", msg)


if __name__ == "__main__":
    unittest.main()

