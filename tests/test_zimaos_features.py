"""Unit tests for ZimaOS server features: Container Sentinel, Model Manager, and Daily Briefing."""

import os
import unittest
from unittest.mock import MagicMock, patch

from config import config
from schemas import CONTAINER_SYSTEM_PROMPT, SYSTEM_PROMPT
from tools.ai_telemetry import manage_ai_models
from tools.zimaos import get_homelab_briefing, manage_containers


class TestZimaOSFeatures(unittest.TestCase):
    """Verifies ZimaOS Docker management, AI model catalog, and Daily Briefing."""

    def test_container_system_prompt_is_concise(self) -> None:
        """Verifies CONTAINER_SYSTEM_PROMPT is streamlined for fast CPU inference."""
        # Baseline desktop prompt is ~3000 tokens (> 10000 chars)
        self.assertGreater(len(SYSTEM_PROMPT), 8000)
        # Container prompt must be under 4000 chars (< 550 tokens, vs 13,000+ chars in full prompt)
        self.assertLess(len(CONTAINER_SYSTEM_PROMPT), 4000)
        self.assertIn("manage_containers", CONTAINER_SYSTEM_PROMPT)
        self.assertIn("manage_ai_models", CONTAINER_SYSTEM_PROMPT)
        self.assertIn("get_homelab_briefing", CONTAINER_SYSTEM_PROMPT)

    def test_manage_containers_list(self) -> None:
        """Verifies container listing returns a valid 70-column ASCII card."""
        ok, res = manage_containers("list")
        self.assertTrue(ok)
        self.assertIsInstance(res, dict)
        self.assertIn("full_terminal_card", res)
        card = res["full_terminal_card"]
        self.assertIn("DOCKER CONTAINER SENTINEL", card)
        # Verify 70-character card boundary width
        first_line = card.splitlines()[0]
        self.assertEqual(len(first_line), 70)

    def test_manage_containers_restart_empty(self) -> None:
        """Verifies restarting without container name returns clean error."""
        ok, msg = manage_containers("restart", "")
        self.assertFalse(ok)
        self.assertIn("Specify a container", msg)

    @patch("tools.zimaos._query_docker_socket")
    def test_manage_containers_restart_success(self, mock_socket) -> None:
        """Verifies container restart invokes docker socket and returns success."""
        mock_socket.side_effect = [
            (200, [{"Id": "abc12345", "Names": ["/jellyfin"]}]),
            (204, ""),
        ]
        ok, msg = manage_containers("restart", "jellyfin")
        self.assertTrue(ok)
        self.assertIn("reanimation protocol", msg.lower())

    @patch("tools.zimaos._query_docker_socket")
    def test_manage_containers_logs(self, mock_socket) -> None:
        """Verifies container log tail retrieval formats cleanly."""
        mock_socket.side_effect = [
            (200, [{"Id": "def67890", "Names": ["/ollama"]}]),
            (200, "2026-09-14 GIN 200 GET /api/tags\n2026-09-14 GIN 200 GET /api/ps"),
        ]
        ok, res = manage_containers("logs", "ollama", lines=10)
        self.assertTrue(ok)
        self.assertIsInstance(res, dict)
        card = res.get("full_terminal_card", "")
        self.assertIn("CONTAINER LOG SENTINEL", card)
        self.assertIn("GET /api/tags", card)

    @patch("requests.get")
    def test_manage_ai_models_list(self, mock_get) -> None:
        """Verifies model catalog queries tags and formats ASCII card."""
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.json.return_value = {
            "models": [
                {
                    "name": "qwen2.5:3b",
                    "size": 1979000000,
                    "details": {"quantization_level": "Q4_K_M", "parameter_size": "3.1B"},
                },
                {
                    "name": "qwen2.5:1.5b",
                    "size": 986000000,
                    "details": {"quantization_level": "Q4_K_M", "parameter_size": "1.5B"},
                },
            ]
        }
        mock_get.return_value = mock_resp

        ok, res = manage_ai_models("list")
        self.assertTrue(ok)
        self.assertIsInstance(res, dict)
        card = res["full_terminal_card"]
        self.assertIn("NEURAL CORE & OLLAMA MODEL CATALOG", card)
        self.assertIn("qwen2.5:3b", card)
        self.assertIn("qwen2.5:1.5b", card)
        first_line = card.splitlines()[0]
        self.assertEqual(len(first_line), 70)

    def test_manage_ai_models_switch(self) -> None:
        """Verifies switching model updates config and returns confirmation."""
        orig_model = config.llm_model
        try:
            ok, res = manage_ai_models("switch", "qwen2.5:1.5b")
            self.assertTrue(ok)
            self.assertEqual(config.llm_model, "qwen2.5:1.5b")
            self.assertIn("reconfigured", res["message"].lower())
        finally:
            config.llm_model = orig_model

    def test_get_homelab_briefing(self) -> None:
        """Verifies daily briefing generates a valid 70-column ASCII report."""
        ok, res = get_homelab_briefing(to_discord=False)
        self.assertTrue(ok)
        self.assertIsInstance(res, dict)
        card = res["full_terminal_card"]
        self.assertIn("APERTURE SCIENCE HOMELAB FACILITY DAILY BRIEFING", card)
        self.assertIn("HOST TELEMETRY", card)
        self.assertIn("CONTAINER SENTINEL", card)
        self.assertIn("GLaDOS MEMORANDUM", card)
        first_line = card.splitlines()[0]
        self.assertEqual(len(first_line), 70)

    def test_agent_query_llm_thread_cap_and_container_prompt(self) -> None:
        """Verifies OSAgent query_llm applies num_thread option and container prompt."""
        from agent import OSAgent

        agent = OSAgent()
        with (
            patch.dict(os.environ, {"CONTAINER_MODE": "true"}),
            patch.object(agent.client.chat.completions, "create") as mock_create,
        ):
            mock_resp = MagicMock()
            mock_choice = MagicMock()
            mock_choice.message.content = '{"thought": "test", "response": "Ready.", "actions": []}'
            mock_resp.choices = [mock_choice]
            mock_resp.usage = None
            mock_create.return_value = mock_resp

            config.container_mode = True
            config.llm_num_threads = 4
            resp = agent.query_llm("test query")
            self.assertEqual(resp.response, "Ready.")

            # Inspect create call arguments
            call_kwargs = mock_create.call_args.kwargs
            extra_body = call_kwargs.get("extra_body", {})
            options = extra_body.get("options", {})
            self.assertEqual(options.get("num_thread"), 4)

            # Inspect system prompt used
            messages = call_kwargs.get("messages", [])
            sys_msg = next((m for m in messages if m["role"] == "system"), None)
            self.assertIsNotNone(sys_msg)
            self.assertEqual(sys_msg["content"], CONTAINER_SYSTEM_PROMPT)
