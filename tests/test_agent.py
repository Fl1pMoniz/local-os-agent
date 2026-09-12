"""Tests for agent plan execution, multi-tool chaining, and safety confirmation callback."""

import unittest
from agent import OSAgent
from schemas import AgentResponse, ToolAction


class TestAgentExecution(unittest.TestCase):
    def test_multi_tool_execution(self):
        """Test sequential execution of multiple non-sensitive tools."""
        plan = AgentResponse(
            thought="Collect stats and capture screenshot",
            actions=[
                ToolAction(tool="get_system_stats", args={}),
                ToolAction(tool="take_screenshot", args={"filename": "chain_test.png"}),
            ],
        )

        agent = OSAgent()
        results = agent.execute_plan(plan)

        self.assertEqual(len(results), 2)
        self.assertEqual(results[0].tool, "get_system_stats")
        self.assertTrue(results[0].success)
        self.assertEqual(results[1].tool, "take_screenshot")
        self.assertTrue(results[1].success)

    def test_safety_gatekeeper_confirmation_approval(self):
        """Test sensitive tool execution when approved by user with thought context."""
        confirmed_context = {}

        def mock_approve(thought: str, tool_name: str, args: dict) -> bool:
            confirmed_context["thought"] = thought
            confirmed_context["tool"] = tool_name
            confirmed_context["args"] = args
            return True  # User approves

        plan = AgentResponse(
            thought="Closing unresponsive notepad process",
            actions=[
                ToolAction(tool="kill_process", args={"name_or_pid": "non_existent_proc_9999"}),
            ],
        )

        agent = OSAgent(confirmation_callback=mock_approve)
        results = agent.execute_plan(plan)

        # Ensure confirmation was requested with thought context
        self.assertEqual(confirmed_context["thought"], "Closing unresponsive notepad process")
        self.assertEqual(confirmed_context["tool"], "kill_process")
        self.assertEqual(len(results), 1)
        # Should have run (not cancelled)
        self.assertNotEqual(results[0].status, "cancelled")

    def test_safety_gatekeeper_confirmation_denial(self):
        """Test sensitive tool cancellation when rejected by user."""
        def mock_deny(thought: str, tool_name: str, args: dict) -> bool:
            return False  # User types 'n' or rejects

        plan = AgentResponse(
            thought="I am shutting down the machine",
            actions=[
                ToolAction(tool="shutdown", args={"delay_seconds": 300}),
            ],
        )

        agent = OSAgent(confirmation_callback=mock_deny)
        results = agent.execute_plan(plan)

        self.assertEqual(len(results), 1)
        self.assertEqual(results[0].status, "cancelled")
        self.assertFalse(results[0].success)
        self.assertIn("declined", results[0].message)


if __name__ == "__main__":
    unittest.main()

