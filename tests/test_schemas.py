"""Tests for JSON extraction, schemas, and exact SYSTEM_PROMPT."""

import unittest
from agent import SYSTEM_PROMPT, extract_json_payload
from schemas import AgentResponse, ToolAction


class TestSchemas(unittest.TestCase):
    def test_system_prompt_exactness(self):
        """Verify the exact SYSTEM_PROMPT text matches prompt specification."""
        self.assertIn("You are GLaDOS (Genetic Lifeform and Disk Operating System)", SYSTEM_PROMPT)
        self.assertIn("1. set_volume(level: int): Sets master system volume (0-100).", SYSTEM_PROMPT)
        self.assertIn("2. change_volume_relative(delta: int): Adjusts volume up or down relatively", SYSTEM_PROMPT)
        self.assertIn("3. set_app_volume(app_name: str, level: int): Sets volume of a specific application (0-100)", SYSTEM_PROMPT)
        self.assertIn("4. mute_toggle(): Toggles the system mute state.", SYSTEM_PROMPT)
        self.assertIn("5. play_youtube(query: str, music: bool = False): Opens YouTube or YouTube Music", SYSTEM_PROMPT)
        self.assertIn("track_flight", SYSTEM_PROMPT)
        self.assertIn("get_zimaos_status", SYSTEM_PROMPT)
        self.assertIn("list_zimaos_apps", SYSTEM_PROMPT)
        self.assertIn("open_zimaos_dashboard", SYSTEM_PROMPT)
        self.assertIn("OUTPUT SCHEMA:", SYSTEM_PROMPT)

    def test_clean_json_parsing(self):
        """Verify parsing clean JSON responses."""
        raw = '{"thought": "Lowering volume", "actions": [{"tool": "set_volume", "args": {"level": 30}}]}'
        parsed = extract_json_payload(raw)
        resp = AgentResponse.model_validate(parsed)
        self.assertEqual(resp.thought, "Lowering volume")
        self.assertEqual(len(resp.actions), 1)
        self.assertEqual(resp.actions[0].tool, "set_volume")
        self.assertEqual(resp.actions[0].args["level"], 30)

    def test_markdown_and_conversational_fluff_extraction(self):
        """Verify robust regex extraction with markdown fences and LLM chatter."""
        raw = (
            "Sure! Here is the JSON you requested:\n\n"
            "```json\n"
            "{\n"
            '  "thought": "I will lower the volume and launch Balatro for you.",\n'
            '  "actions": [\n'
            '    {"tool": "set_volume", "args": {"level": 25}},\n'
            '    {"tool": "launch_steam_game", "args": {"game_name": "Balatro"}}\n'
            "  ]\n"
            "}\n"
            "```\n"
            "Let me know if you need anything else!"
        )
        parsed = extract_json_payload(raw)
        resp = AgentResponse.model_validate(parsed)
        self.assertEqual(resp.thought, "I will lower the volume and launch Balatro for you.")
        self.assertEqual(len(resp.actions), 2)
        self.assertEqual(resp.actions[0].tool, "set_volume")
        self.assertEqual(resp.actions[0].args["level"], 25)
        self.assertEqual(resp.actions[1].tool, "launch_steam_game")
        self.assertEqual(resp.actions[1].args["game_name"], "Balatro")

    def test_empty_actions(self):
        """Verify handling of empty action lists when request is out of scope."""
        raw = '{"thought": "I cannot write an essay directly with OS tools.", "actions": []}'
        parsed = extract_json_payload(raw)
        resp = AgentResponse.model_validate(parsed)
        self.assertEqual(len(resp.actions), 0)


if __name__ == "__main__":
    unittest.main()

