"""Unit tests for offline deterministic survival fallback resolver."""

from __future__ import annotations

import unittest

from app.agent.fallback import OfflineFallbackResolver


class TestOfflineFallback(unittest.TestCase):
    """Test suite ensuring survival commands resolve without LLM intervention."""

    def setUp(self) -> None:
        self.resolver = OfflineFallbackResolver()

    def test_emergency_audio_stop(self) -> None:
        """Verifies emergency audio termination commands."""
        queries = ["stop", "stop song", "STOP", "shut up", "parar", "silence"]
        for q in queries:
            res = self.resolver.resolve(q)
            self.assertIsNotNone(res, f"Failed on query: {q}")
            self.assertEqual(res.tool, "stop_song")

    def test_mute_toggle(self) -> None:
        """Verifies mute toggle queries."""
        queries = ["mute", "unmute", "silenciar", "mudo"]
        for q in queries:
            res = self.resolver.resolve(q)
            self.assertIsNotNone(res, f"Failed on query: {q}")
            self.assertEqual(res.tool, "mute_toggle")

    def test_workstation_lock(self) -> None:
        """Verifies session lock queries."""
        queries = ["lock", "lock workstation", "lock screen", "lock computer", "trancar tela"]
        for q in queries:
            res = self.resolver.resolve(q)
            self.assertIsNotNone(res, f"Failed on query: {q}")
            self.assertEqual(res.tool, "lock_workstation")

    def test_exact_volume(self) -> None:
        """Verifies exact volume extraction."""
        res = self.resolver.resolve("set volume to 40")
        self.assertIsNotNone(res)
        self.assertEqual(res.tool, "set_volume")
        self.assertEqual(res.args.get("level"), 40)

        res2 = self.resolver.resolve("volume 85%")
        self.assertIsNotNone(res2)
        self.assertEqual(res2.tool, "set_volume")
        self.assertEqual(res2.args.get("level"), 85)

    def test_relative_volume(self) -> None:
        """Verifies relative volume adjustments."""
        up_res = self.resolver.resolve("volume up")
        self.assertIsNotNone(up_res)
        self.assertEqual(up_res.tool, "change_volume_relative")
        self.assertEqual(up_res.args.get("delta"), 10)

        down_res = self.resolver.resolve("turn it down")
        self.assertIsNotNone(down_res)
        self.assertEqual(down_res.tool, "change_volume_relative")
        self.assertEqual(down_res.args.get("delta"), -10)

    def test_system_stats(self) -> None:
        """Verifies diagnostics commands."""
        queries = ["stats", "system stats", "pc stats", "status do sistema"]
        for q in queries:
            res = self.resolver.resolve(q)
            self.assertIsNotNone(res, f"Failed on query: {q}")
            self.assertEqual(res.tool, "get_system_stats")

    def test_screenshot(self) -> None:
        """Verifies optical screen capture command."""
        res = self.resolver.resolve("take screenshot")
        self.assertIsNotNone(res)
        self.assertEqual(res.tool, "take_screenshot")

    def test_recycle_bin(self) -> None:
        """Verifies recycle bin purge command."""
        res = self.resolver.resolve("empty recycle bin")
        self.assertIsNotNone(res)
        self.assertEqual(res.tool, "empty_recycle_bin")

    def test_complex_natural_language_not_intercepted(self) -> None:
        """Verifies complex, conversational queries pass through to the LLM."""
        queries = [
            "Why is the cake a lie?",
            "Track flight DL450 and show me altitude",
            "Can you open Chrome and search for quantum physics?",
            "Sing still alive for me",
        ]
        for q in queries:
            res = self.resolver.resolve(q)
            self.assertIsNone(res, f"Unexpectedly intercepted query: {q}")
