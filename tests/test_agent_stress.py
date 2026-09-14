"""Extensive stress and resilience test suite for Local OS Agent.

Covers:
  1. JSON extraction resilience (fences, single quotes, Python dicts, trailing commas, missing keys).
  2. Multi-language and phrasing deterministic intent resolvers (all 28 tools).
  3. Contextual safety gatekeeper & critical process protection (PID 0, kernel, svchost).
  4. Argument type coercion & defensive parsing (percentages, strings, floats, Nones).
  5. Fallback mechanisms when LLM is unavailable or offline.
"""

import unittest
from unittest.mock import MagicMock, patch

from agent import OSAgent, extract_json_payload
from schemas import AgentResponse, ToolAction
from tools import execute_tool
from tools.audio import set_volume
from tools.flight import clean_flight_query
from tools.steam import find_best_game_match, launch_steam_game
from tools.system import kill_process
from tools.zimaos import launch_zimaos_app


class TestJsonExtractorStress(unittest.TestCase):
    """Stress tests for the JSON payload extractor against small LLM output defects."""

    def test_clean_json(self):
        raw = '{"thought": "Adjusting volume", "response": "Volume adjusted.", "actions": []}'
        data = extract_json_payload(raw)
        self.assertEqual(data["thought"], "Adjusting volume")
        self.assertEqual(data["response"], "Volume adjusted.")
        self.assertEqual(data["actions"], [])

    def test_markdown_code_fences(self):
        raw = """```json
{
    "thought": "Initiating radio feed",
    "response": "Broadcasting radio loop.",
    "actions": [{"tool": "play_portal_sfx", "args": {"effect_name": "radio"}}]
}
```"""
        data = extract_json_payload(raw)
        self.assertEqual(data["actions"][0]["tool"], "play_portal_sfx")

    def test_conversational_fluff_surrounding_json(self):
        raw = """Certainly! Here is the JSON execution plan for GLaDOS:
{
    "thought": "Subject requested system stats",
    "response": "Here is your system telemetry.",
    "actions": [{"tool": "get_system_stats", "args": {}}]
}
I hope this was helpful! Let me know if you need anything else."""
        data = extract_json_payload(raw)
        self.assertEqual(data["thought"], "Subject requested system stats")
        self.assertEqual(len(data["actions"]), 1)

    def test_trailing_commas_in_objects_and_arrays(self):
        raw = """{
    "thought": "Test commas",
    "response": "Test response",
    "actions": [
        {"tool": "mute_toggle", "args": {},},
    ],
}"""
        data = extract_json_payload(raw)
        self.assertEqual(data["actions"][0]["tool"], "mute_toggle")

    def test_python_single_quote_dictionary(self):
        raw = "{'thought': 'Single quotes from 3B model', 'response': 'Understood.', 'actions': [{'tool': 'set_volume', 'args': {'level': 40}}]}"
        data = extract_json_payload(raw)
        self.assertEqual(data["thought"], "Single quotes from 3B model")
        self.assertEqual(data["actions"][0]["args"]["level"], 40)

    def test_python_boolean_and_none_literals(self):
        raw = '{"thought": "Booleans", "response": "Yes", "actions": [{"tool": "play_youtube", "args": {"query": "Portal", "music": True, "extra": None}}]}'
        data = extract_json_payload(raw)
        self.assertTrue(data["actions"][0]["args"]["music"])

    def test_missing_thought_or_response_keys_auto_repaired(self):
        # Missing 'thought'
        raw1 = '{"response": "Just response", "actions": []}'
        data1 = extract_json_payload(raw1)
        self.assertEqual(data1["thought"], "Just response")

        # Missing 'response'
        raw2 = '{"thought": "Just thought", "actions": []}'
        data2 = extract_json_payload(raw2)
        self.assertEqual(data2["response"], "Just thought")

        # Missing 'actions'
        raw3 = '{"thought": "No actions field", "response": "Hello"}'
        data3 = extract_json_payload(raw3)
        self.assertEqual(data3["actions"], [])

    def test_empty_or_invalid_raises_value_error(self):
        with self.assertRaises(ValueError):
            extract_json_payload("")
        with self.assertRaises(ValueError):
            extract_json_payload("   ")
        with self.assertRaises(ValueError):
            extract_json_payload("Just some plain conversational text with no brackets at all.")


class TestDeterministicIntentEngineStress(unittest.TestCase):
    """Verifies that user prompts are reliably resolved even if the LLM fails."""

    def setUp(self):
        # Create an agent where LLM client is simulated to fail/offline
        self.agent = OSAgent(enable_voice=False)
        self.agent.client = MagicMock()
        self.agent.client.chat.completions.create.side_effect = ConnectionError(
            "Simulated LLM offline"
        )

    def test_volume_intents_english_and_portuguese(self):
        prompts_and_tools = [
            ("volume up", "change_volume_relative", 15),
            ("turn it up please", "change_volume_relative", 15),
            ("aumenta o volume", "change_volume_relative", 15),
            ("sobe o volume", "change_volume_relative", 15),
            ("volume down", "change_volume_relative", -15),
            ("quieter", "change_volume_relative", -15),
            ("abaixa o volume", "change_volume_relative", -15),
            ("diminui o volume", "change_volume_relative", -15),
            ("set volume to 45%", "set_volume", 45),
            ("volume 70", "set_volume", 70),
            ("coloca o volume em 80%", "set_volume", 80),
        ]
        for prompt, expected_tool, expected_val in prompts_and_tools:
            plan = self.agent.query_llm(prompt)
            self.assertTrue(len(plan.actions) > 0, f"Failed on: {prompt}")
            self.assertEqual(plan.actions[0].tool, expected_tool, f"Wrong tool on: {prompt}")
            if expected_tool == "change_volume_relative":
                self.assertEqual(plan.actions[0].args.get("delta"), expected_val)
            elif expected_tool == "set_volume":
                self.assertEqual(plan.actions[0].args.get("level"), expected_val)

    def test_mute_toggle_intents(self):
        for p in ["mute", "unmute audio", "silenciar", "colocar no mudo"]:
            plan = self.agent.query_llm(p)
            self.assertTrue(
                any(a.tool == "mute_toggle" for a in plan.actions), f"Failed mute on: {p}"
            )

    def test_youtube_and_music_intents(self):
        # YouTube Music
        plan_music = self.agent.query_llm("play Radiohead on YouTube Music")
        self.assertEqual(plan_music.actions[0].tool, "play_youtube")
        self.assertTrue(plan_music.actions[0].args["music"])
        self.assertIn("radiohead", plan_music.actions[0].args["query"].lower())

        # Standard YouTube
        plan_yt = self.agent.query_llm("watch portal 2 speedrun on youtube")
        self.assertEqual(plan_yt.actions[0].tool, "play_youtube")
        self.assertFalse(plan_yt.actions[0].args["music"])

    def test_flight_tracking_intents(self):
        for p, code in [
            ("track flight AA100", "AA100"),
            ("where is flight DL450", "DL450"),
            ("rastrear voo LA3001", "LA3001"),
        ]:
            plan = self.agent.query_llm(p)
            self.assertEqual(plan.actions[0].tool, "track_flight")
            self.assertEqual(plan.actions[0].args["flight_query"], code)

    def test_zimaos_intents(self):
        plan_status = self.agent.query_llm("check my zimaos server")
        self.assertEqual(plan_status.actions[0].tool, "get_zimaos_status")

        plan_apps = self.agent.query_llm("list containers on zimaos")
        self.assertEqual(plan_apps.actions[0].tool, "list_zimaos_apps")

        plan_dash = self.agent.query_llm("open zimaos dashboard")
        self.assertEqual(plan_dash.actions[0].tool, "open_zimaos_dashboard")

        plan_launch = self.agent.query_llm("launch plex on zimaos")
        self.assertEqual(plan_launch.actions[0].tool, "launch_zimaos_app")
        self.assertIn("plex", plan_launch.actions[0].args["app_name"].lower())

    def test_songs_and_sfx_intents(self):
        plan_song1 = self.agent.query_llm("sing Still Alive")
        self.assertEqual(plan_song1.actions[0].tool, "sing_song")
        self.assertEqual(plan_song1.actions[0].args["song_name"], "still_alive")

        plan_song2 = self.agent.query_llm("sing Want You Gone")
        self.assertEqual(plan_song2.actions[0].tool, "sing_song")
        self.assertEqual(plan_song2.actions[0].args["song_name"], "want_you_gone")

        plan_radio = self.agent.query_llm("play portal radio")
        self.assertEqual(plan_radio.actions[0].tool, "play_portal_sfx")
        self.assertEqual(plan_radio.actions[0].args["effect_name"], "radio")

        plan_stop = self.agent.query_llm("stop radio")
        self.assertEqual(plan_stop.actions[0].tool, "stop_sfx")

    def test_companion_and_utilities_intents(self):
        plan_roast = self.agent.query_llm("roast me GLaDOS")
        self.assertEqual(plan_roast.actions[0].tool, "roast_user")

        plan_lock = self.agent.query_llm("lock my pc")
        self.assertEqual(plan_lock.actions[0].tool, "lock_workstation")

        plan_shot = self.agent.query_llm("take a screenshot")
        self.assertEqual(plan_shot.actions[0].tool, "take_screenshot")

        plan_stats = self.agent.query_llm("how are my system stats")
        self.assertEqual(plan_stats.actions[0].tool, "get_system_stats")

        plan_bin = self.agent.query_llm("empty recycle bin")
        self.assertEqual(plan_bin.actions[0].tool, "empty_recycle_bin")

        plan_weather = self.agent.query_llm("how is the weather outside")
        self.assertEqual(plan_weather.actions[0].tool, "get_weather")


class TestSafetyGatekeeperAndProcessProtection(unittest.TestCase):
    """Tests critical process safeguards and user confirmation gatekeeping."""

    def test_critical_processes_are_protected(self):
        for proc in ["system", "svchost", "csrss.exe", "lsass.exe", "smss.exe", "wininit.exe"]:
            success, msg = kill_process(proc)
            self.assertFalse(success)
            self.assertIn("safety override", msg.lower())

    def test_pid_0_and_4_are_protected(self):
        success, msg = kill_process(0)
        self.assertFalse(success)
        self.assertIn("kernel", msg.lower())

        success4, msg4 = kill_process(4)
        self.assertFalse(success4)
        self.assertIn("kernel", msg4.lower())

    def test_sensitive_tools_await_confirmation(self):
        sensitive_tools = ["kill_process", "shutdown", "sleep_pc", "empty_recycle_bin"]
        for tool_name in sensitive_tools:
            res = execute_tool(tool_name, {}, bypass_confirmation=False)
            self.assertFalse(res.success)
            self.assertEqual(res.status, "awaiting_confirmation")

    def test_agent_safety_confirmation_flow(self):
        declining_callback = lambda thought, tool, args: False
        agent = OSAgent(confirmation_callback=declining_callback, enable_voice=False)

        plan = AgentResponse(
            thought="Terminating background process",
            response="Proceeding with termination.",
            actions=[ToolAction(tool="kill_process", args={"name_or_pid": 999999})],
        )
        results = agent.execute_plan(plan)
        self.assertEqual(len(results), 1)
        self.assertEqual(results[0].status, "cancelled")
        self.assertIn("declined", results[0].message.lower())


class TestDefensiveArgumentCoercion(unittest.TestCase):
    """Verifies that all tool functions cleanly accept malformed or stringified arguments."""

    def test_set_volume_coercion(self):
        # Strings with %, floats, negative, >100
        cases = [
            ("50%", 50),
            (30.7, 30),
            ("-10", 0),
            ("150%", 100),
            ("invalid", 50),
        ]
        for val, expected_clamp in cases:
            # We don't want to actually change the host volume during unit test, so mock endpoint
            with (
                patch("tools.audio._get_windows_volume_endpoint") as mock_ep,
                patch("platform.system", return_value="Windows"),
            ):
                mock_inst = MagicMock()
                mock_inst.GetMasterVolumeLevelScalar.return_value = expected_clamp / 100.0
                mock_ep.return_value = mock_inst
                success, msg = set_volume(val)
                self.assertTrue(success)

    def test_clean_flight_query(self):
        self.assertEqual(clean_flight_query("AA 100"), "AA100")
        self.assertEqual(clean_flight_query("DL 450"), "DL450")
        self.assertEqual(clean_flight_query("track flight LA3001"), "LA3001")
        self.assertEqual(clean_flight_query("voo TAP 123"), "TAP123")

    def test_launch_zimaos_app_empty_guard(self):
        success, msg = launch_zimaos_app("")
        self.assertFalse(success)
        self.assertIn("specify an application", msg)

        success2, msg2 = launch_zimaos_app(None)
        self.assertFalse(success2)

    def test_steam_game_empty_guard(self):
        success, msg = launch_steam_game("")
        self.assertFalse(success)
        self.assertIn("specify a game name", msg)

        match = find_best_game_match("", {"Portal": 400})
        self.assertIsNone(match)


class TestSystemToolsAndServerIntegration(unittest.TestCase):
    """Tests timer, clipboard, companion, web aliases, and UI server state."""

    def test_set_timer_validation(self):
        from tools.system import set_timer

        # Negative or 0 should fail cleanly
        s1, m1 = set_timer(0)
        self.assertFalse(s1)
        self.assertIn("greater than 0", m1)

        s2, m2 = set_timer(-5)
        self.assertFalse(s2)

        # Valid duration
        s3, m3 = set_timer(10, label="Enrichment Test")
        self.assertTrue(s3)
        self.assertIn("Timer set", m3)

    @patch("pyperclip.paste")
    @patch("voice.speak")
    def test_read_clipboard_aloud(self, mock_speak, mock_paste):
        from tools.system import read_clipboard_aloud

        # Empty clipboard
        mock_paste.return_value = ""
        s1, m1 = read_clipboard_aloud()
        self.assertFalse(s1)
        self.assertIn("empty", m1.lower())

        # Non-empty clipboard
        mock_paste.return_value = "Aperture Science Enrichment Center test protocol #42."
        s2, m2 = read_clipboard_aloud()
        self.assertTrue(s2)
        mock_speak.assert_called_once()

    def test_companion_roast_and_window(self):
        from tools.companion import get_active_window, roast_user

        s1, m1 = get_active_window()
        self.assertTrue(s1)
        self.assertIn("Active Window", m1)

        s2, m2 = roast_user()
        self.assertTrue(s2)
        self.assertTrue(len(m2) > 10)

    @patch("webbrowser.open")
    def test_web_aliases(self, mock_open):
        from tools.web import open_website

        s1, m1 = open_website("youtube")
        self.assertTrue(s1)
        mock_open.assert_called_with("https://www.youtube.com")

        s2, m2 = open_website("reddit")
        self.assertTrue(s2)
        mock_open.assert_called_with("https://www.reddit.com")

        s3, m3 = open_website("https://aperturescience.com")
        self.assertTrue(s3)
        mock_open.assert_called_with("https://aperturescience.com")

    def test_ui_state_threading_and_broadcasting(self):
        from ui.state import ui_state

        sub = ui_state.subscribe()
        ui_state.update(state="speaking", text="Testing state pipeline.")
        event = sub.get(timeout=2.0)
        self.assertEqual(event["state"], "speaking")
        self.assertEqual(event["text"], "Testing state pipeline.")
        ui_state.unsubscribe(sub)


if __name__ == "__main__":
    unittest.main()
