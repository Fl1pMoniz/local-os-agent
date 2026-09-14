"""Unit tests for GLaDOS AI Core Telemetry & Neural Inference Performance Tracker."""

import unittest

from agent import OSAgent
from tools import execute_tool, get_tool
from tools.ai_telemetry import (
    AITelemetryTracker,
    format_glados_ai_hud,
)


class TestAITelemetry(unittest.TestCase):
    """Verifies AI RAM tracking, token production, inference speed, and ASCII HUD formatting."""

    def setUp(self):
        self.tracker = AITelemetryTracker()

    def test_record_inference_metrics(self):
        """Verifies recording inference prompt tokens, output tokens, latency, and tok/s."""
        self.assertEqual(self.tracker.total_tokens, 0)
        self.assertEqual(self.tracker.total_queries, 0)

        # Record first inference: 50 prompt tokens, 25 completion tokens, 0.5 seconds
        self.tracker.record_inference(
            prompt_tokens=50,
            completion_tokens=25,
            latency_s=0.5,
            model="glados:3b",
        )

        self.assertEqual(self.tracker.total_prompt_tokens, 50)
        self.assertEqual(self.tracker.total_completion_tokens, 25)
        self.assertEqual(self.tracker.total_tokens, 75)
        self.assertEqual(self.tracker.total_queries, 1)
        self.assertEqual(self.tracker.last_prompt_tokens, 50)
        self.assertEqual(self.tracker.last_completion_tokens, 25)
        self.assertEqual(self.tracker.last_tokens_per_sec, 50.0)  # 25 / 0.5 = 50 tok/s
        self.assertEqual(self.tracker.peak_tokens_per_sec, 50.0)

        # Record second inference: 100 prompt tokens, 50 completion tokens, 1.0 second
        self.tracker.record_inference(
            prompt_tokens=100,
            completion_tokens=50,
            latency_s=1.0,
            model="glados:3b",
        )

        self.assertEqual(self.tracker.total_prompt_tokens, 150)
        self.assertEqual(self.tracker.total_completion_tokens, 75)
        self.assertEqual(self.tracker.total_tokens, 225)
        self.assertEqual(self.tracker.total_queries, 2)
        self.assertEqual(self.tracker.last_tokens_per_sec, 50.0)
        # Average: 75 / 1.5s = 50.0 tok/s
        self.assertEqual(self.tracker.avg_tokens_per_sec, 50.0)

    def test_get_ai_ram_usage(self):
        """Verifies AI RAM memory discovery returns valid MB numbers."""
        ram_data = self.tracker.get_ai_ram_usage()
        self.assertIsInstance(ram_data, dict)
        self.assertIn("total_ai_ram_mb", ram_data)
        self.assertIn("llm_runner_ram_mb", ram_data)
        self.assertIn("host_agent_ram_mb", ram_data)
        self.assertIn("runner_name", ram_data)
        self.assertGreaterEqual(ram_data["total_ai_ram_mb"], 0.0)
        self.assertGreater(ram_data["host_agent_ram_mb"], 0.0)  # Current Python process memory

    def test_get_ollama_model_info(self):
        """Verifies Ollama model info returns fallback dictionary if endpoint is offline or mocked."""
        info = self.tracker.get_ollama_model_info()
        self.assertIsInstance(info, dict)
        self.assertIn("name", info)
        self.assertIn("parameter_size", info)
        self.assertIn("quantization", info)
        self.assertIn("status", info)
        self.assertIn("context_length", info)

    def test_get_telemetry_payload(self):
        """Verifies full telemetry dictionary structure."""
        self.tracker.record_inference(prompt_tokens=40, completion_tokens=20, latency_s=0.4)
        telemetry = self.tracker.get_telemetry()
        self.assertIsInstance(telemetry, dict)
        self.assertEqual(telemetry["prompt_tokens"], 40)
        self.assertEqual(telemetry["completion_tokens"], 20)
        self.assertEqual(telemetry["total_tokens_produced"], 60)
        self.assertEqual(telemetry["tokens_per_sec"], 50.0)
        self.assertIn("ai_ram_total_mb", telemetry)
        self.assertIn("model_name", telemetry)
        self.assertIn("voice_subsystem", telemetry)
        self.assertIn("vision_subsystem", telemetry)

    def test_format_glados_ai_hud_dimensions(self):
        """Verifies the GLaDOS AI HUD card formatting strictly adheres to 70-character columns."""
        test_data = {
            "model_name": "glados:3b",
            "parameter_size": "3.2B",
            "quantization": "Q4_K_M",
            "model_vram_mb": 2962,
            "model_status": "ONLINE",
            "ai_ram_total_mb": 1149.2,
            "ai_ram_runner_mb": 1131.4,
            "ai_ram_host_mb": 17.8,
            "ai_runner_name": "Ollama",
            "total_tokens_produced": 4820,
            "prompt_tokens": 1419,
            "completion_tokens": 3401,
            "total_queries": 12,
            "last_prompt_tokens": 140,
            "last_completion_tokens": 65,
            "last_latency_ms": 145.0,
            "tokens_per_sec": 38.4,
            "peak_tokens_per_sec": 42.1,
            "avg_tokens_per_sec": 36.2,
            "context_tokens": 348,
            "context_max": 8192,
            "context_percent": 4.2,
            "voice_subsystem": "Piper VITS GLaDOS",
            "vision_subsystem": "Optical Active",
        }

        lines = format_glados_ai_hud(test_data)
        self.assertGreater(len(lines), 5)
        for idx, line in enumerate(lines):
            self.assertEqual(
                len(line), 70, f"Line {idx} width mismatch ({len(line)} != 70): {line}"
            )
            self.assertTrue(line.startswith("|") or line.startswith("+"))
            self.assertTrue(line.endswith("|") or line.endswith("+"))

        joined = "\n".join(lines)
        self.assertIn("GLaDOS AI NEURAL CORE & INFERENCE TELEMETRY", joined)
        self.assertIn("glados:3b", joined)
        self.assertIn("1,149.2 MB", joined)
        self.assertIn("38.4 tok/s", joined)
        self.assertIn("4,820 produced", joined)

    def test_tool_registration_and_execution(self):
        """Verifies get_glados_ai_stats is properly registered in toolset."""
        tool_def = get_tool("get_glados_ai_stats")
        self.assertIsNotNone(tool_def)
        self.assertEqual(tool_def.name, "get_glados_ai_stats")

        res = execute_tool("get_glados_ai_stats")
        self.assertTrue(res.success)
        self.assertIn("metrics", res.data)
        self.assertIn("terminal_card", res.data)
        self.assertIn("GLaDOS AI NEURAL CORE & INFERENCE TELEMETRY", res.data["terminal_card"])

    def test_agent_intent_recognition_ai_stats(self):
        """Verifies agent routes 'ai stats' and 'glados stats' to monitor_hardware."""
        agent = OSAgent(model="glados:3b")

        for query in ("ai stats", "glados stats", "show ai telemetry", "ai ram", "tokens per sec"):
            plan = agent.query_llm(query)
            self.assertTrue(
                any(
                    a.tool in ("monitor_hardware", "get_system_stats", "get_glados_ai_stats")
                    for a in plan.actions
                ),
                f"Query '{query}' did not dispatch hardware/ai telemetry tool.",
            )


if __name__ == "__main__":
    unittest.main()
