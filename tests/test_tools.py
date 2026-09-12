"""Tests for core tools: system stats, screenshots, audio, and tool registry."""

import unittest
from pathlib import Path
from tools import execute_tool, get_tool, list_tools


class TestTools(unittest.TestCase):
    def test_registry_contains_required_tools(self):
        tools = list_tools()
        required = [
            "set_volume",
            "set_app_volume",
            "list_app_volumes",
            "mute_toggle",
            "play_youtube",
            "media_control",
            "launch_app",
            "launch_steam_game",
            "get_system_stats",
            "take_screenshot",
            "minimize_all_windows",
            "kill_process",
            "shutdown",
            "sleep_pc",
        ]
        for req in required:
            self.assertIn(req, tools, f"Required tool '{req}' not found in registry.")

    def test_sensitive_flagging(self):
        """Verify safety gatekeeper flags sensitive tools."""
        sensitive_expected = ["kill_process", "shutdown", "sleep_pc"]
        for tool_name in sensitive_expected:
            t = get_tool(tool_name)
            self.assertIsNotNone(t)
            self.assertTrue(t.sensitive, f"Tool '{tool_name}' should be marked sensitive.")

    def test_system_stats(self):
        res = execute_tool("get_system_stats")
        self.assertTrue(res.success)
        self.assertIn("cpu", res.data)
        self.assertIn("ram", res.data)
        self.assertIn("battery", res.data)
        self.assertGreaterEqual(res.data["cpu"]["percent_used"], 0.0)

    def test_screenshot_generation(self):
        res = execute_tool("take_screenshot", {"filename": "test_screenshot_unit.png"})
        self.assertTrue(res.success)
        self.assertIn("Screenshot successfully saved", res.message)

    def test_media_control_validation(self):
        # Invalid action should fail gracefully
        res = execute_tool("media_control", {"action": "invalid_command_xyz"})
        self.assertFalse(res.success)
        self.assertIn("Unknown media action", res.message)


if __name__ == "__main__":
    unittest.main()

