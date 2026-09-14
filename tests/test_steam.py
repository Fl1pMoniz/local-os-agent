"""Tests for Steam VDF parsing and fuzzy game matching."""

import unittest

from tools.steam import discover_installed_steam_games, find_best_game_match


class TestSteamDiscovery(unittest.TestCase):
    def setUp(self):
        self.sample_catalog = {
            "Balatro": 2379780,
            "Portal 2": 620,
            "Call of Duty: Modern Warfare 2 (2009)": 10180,
            "Hollow Knight: Silksong": 1030300,
            "Grand Theft Auto V": 271590,
            "Elden Ring": 1245620,
        }

    def test_exact_match(self):
        match = find_best_game_match("balatro", self.sample_catalog)
        self.assertIsNotNone(match)
        self.assertEqual(match[0], "Balatro")
        self.assertEqual(match[1], 2379780)

    def test_substring_match(self):
        match = find_best_game_match("Modern Warfare 2", self.sample_catalog)
        self.assertIsNotNone(match)
        self.assertEqual(match[0], "Call of Duty: Modern Warfare 2 (2009)")
        self.assertEqual(match[1], 10180)

    def test_fuzzy_match(self):
        match = find_best_game_match("Silksong", self.sample_catalog)
        self.assertIsNotNone(match)
        self.assertEqual(match[0], "Hollow Knight: Silksong")
        self.assertEqual(match[1], 1030300)

    def test_typo_fuzzy_match(self):
        match = find_best_game_match("Portl 2", self.sample_catalog)
        self.assertIsNotNone(match)
        self.assertEqual(match[0], "Portal 2")
        self.assertEqual(match[1], 620)

    def test_real_steam_discovery(self):
        """Test against real local Steam installation if present."""
        games = discover_installed_steam_games()
        # If Steam is installed on this host machine, verify we found real games
        if games:
            self.assertIsInstance(games, dict)
            for name, appid in games.items():
                self.assertIsInstance(name, str)
                self.assertIsInstance(appid, int)


if __name__ == "__main__":
    unittest.main()
