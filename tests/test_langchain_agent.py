"""Unit tests for LangChain tool-calling agent implementation."""

from __future__ import annotations

import unittest
from unittest.mock import MagicMock

from langchain_core.messages import AIMessage

from app.agent.langchain_agent import LangChainOSAgent
from app.core.config import AppSettings


class TestLangChainAgent(unittest.TestCase):
    """Test suite for LangChainOSAgent conversational loop and tool execution."""

    def setUp(self) -> None:
        self.settings = AppSettings(headless_mode=True)
        self.agent = LangChainOSAgent(app_settings=self.settings)

    def test_blank_prompt_handling(self) -> None:
        """Verifies blank prompt returns polite error prompt without crashing."""
        self.assertIn("cannot be blank", self.agent.run(""))
        self.assertIn("cannot be blank", self.agent.run("   "))

    def test_offline_fallback_execution(self) -> None:
        """Verifies survival commands execute directly without querying LLM."""
        res = self.agent.run("mute")
        self.assertIn("toggled", res.lower())

        res_stop = self.agent.run("stop")
        self.assertIn("halted", res_stop.lower())

        res_lock = self.agent.run("lock workstation")
        self.assertIn("secured", res_lock.lower())

    def test_tool_calling_invocation_mocked(self) -> None:
        """Verifies agent processes tool calls emitted by LLM and executes tools."""
        mock_ai_msg = AIMessage(
            content="",
            tool_calls=[
                {
                    "name": "set_volume_tool",
                    "args": {"level": 75},
                    "id": "call_mock_1",
                }
            ],
        )

        mock_final_msg = AIMessage(
            content="Master volume adjusted to 75 percent. Sarcasm included."
        )

        self.agent.llm_with_tools = MagicMock()
        self.agent.llm_with_tools.invoke.return_value = mock_ai_msg

        self.agent.llm = MagicMock()
        self.agent.llm.invoke.return_value = mock_final_msg

        response = self.agent.run("Can you set the volume to 75?")
        self.assertEqual(response, "Master volume adjusted to 75 percent. Sarcasm included.")

    def test_pure_conversational_response_mocked(self) -> None:
        """Verifies agent returns text directly when no tool calls are generated."""
        mock_ai_msg = AIMessage(
            content="Cake and grief counseling will be available at the conclusion of the test.",
            tool_calls=[],
        )

        self.agent.llm_with_tools = MagicMock()
        self.agent.llm_with_tools.invoke.return_value = mock_ai_msg

        response = self.agent.run("Tell me about the cake.")
        self.assertIn("Cake and grief counseling", response)
