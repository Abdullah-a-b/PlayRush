"""عقود نموذج الخلايا: قانونية القرار وحدود المستويات وسلامة الخطط."""
import copy
import math
import random
import unittest
from unittest.mock import patch

from app.domains.games.huroof import strategy_policy as policy


def board(green=(), orange=()):
    return [{"color": "green" if i in green else "orange" if i in orange else "white"} for i in range(25)]


class HuroofStrategyPolicyTests(unittest.TestCase):
    def test_distribution_legal_and_does_not_mutate_board(self):
        value = board([0, 5, 12], [4, 8, 17])
        snapshot = copy.deepcopy(value)
        for level in ("beginner", "medium", "hard", "expert"):
            distribution = policy.probabilities(value, "green", level)
            self.assertIsNotNone(distribution)
            self.assertAlmostEqual(sum(p for _, p in distribution), 1)
            self.assertTrue(all(value[i]["color"] == "white" and 0 <= p <= 1 for i, p in distribution))
        self.assertEqual(value, snapshot)

    def test_beginner_stays_nearly_uniform_when_winning_cell_exists(self):
        distribution = policy.probabilities(board([0, 5, 10, 15]), "green", "beginner")
        uniform = 1 / len(distribution)
        self.assertLess(max(abs(p-uniform) for _, p in distribution), .002)

    def test_expert_immediate_win_and_block_are_preserved(self):
        for color in ("green", "orange"):
            win = board([0, 5, 10, 15]) if color == "green" else board([], [0, 1, 2, 3])
            _, _, tags = policy.candidates(win, color)
            distribution = policy.probabilities(win, color, "expert")
            self.assertAlmostEqual(sum(p for (_, p), tag in zip(distribution, tags) if tag["win"]), 1)
            defense = board([], [0, 1, 2, 3]) if color == "green" else board([0, 5, 10, 15])
            _, _, tags = policy.candidates(defense, color)
            distribution = policy.probabilities(defense, color, "expert")
            self.assertAlmostEqual(sum(p for (_, p), tag in zip(distribution, tags) if tag["block"]), 1)

    def test_expert_only_exposes_near_best_non_tactical_options(self):
        value = board([2, 12], [5, 6])
        _, _, tags = policy.candidates(value, "green")
        self.assertFalse(any(tag["win"] or tag["block"] for tag in tags))
        distribution = policy.probabilities(value, "green", "expert")
        best = max(tag["score"] for tag in tags)
        for (_, probability), tag in zip(distribution, tags):
            if probability > 0:
                self.assertGreaterEqual(tag["score"], best-.5)

    def test_model_missing_or_corrupt_uses_fallback_contract(self):
        with patch.object(policy, "load_policy", return_value=None):
            self.assertIsNone(policy.choose(board(), "green", "expert"))
        for broken in ({}, {"architecture": [20,32,1], "levels": {"expert": {"weights": [[], [], [[]], [math.nan]]}}}):
            with patch.object(policy, "load_policy", return_value=broken):
                self.assertIsNone(policy.choose(board(), "green", "expert"))

    def test_sampling_does_not_force_top_choice_or_external_preference(self):
        with patch.object(policy, "probabilities", return_value=[(3, .1), (7, .9)]):
            before = random.getstate()
            try:
                random.seed(71023)
                samples = [policy.choose(board(), "green", "medium", preferred=7) for _ in range(1000)]
            finally:
                random.setstate(before)
            self.assertGreater(samples.count(3), 65)
            self.assertLess(samples.count(3), 140)
            self.assertEqual(set(samples), {3, 7})

    def test_game_entrypoint_uses_model_and_retains_legal_fallback(self):
        from app.domains.games.huroof import solo_bot
        value = board([0, 5, 10, 15])
        with patch.object(policy, "choose", return_value=20):
            self.assertEqual(solo_bot.choose_hex(value, "green", "beginner"), 20)
        with patch.object(policy, "load_policy", return_value=None):
            selected = solo_bot.choose_hex(value, "green", "expert")
            self.assertEqual(value[selected]["color"], "white")
            colors = [c["color"] for c in value]
            self.assertTrue(solo_bot._completes_win(colors, selected, "green"))

    def test_terminal_or_invalid_boards_fall_back(self):
        self.assertIsNone(policy.choose(board(range(25)), "green", "expert"))
        self.assertIsNone(policy.choose([], "green", "expert"))
        self.assertIsNone(policy.choose(board(), "invalid", "expert"))
        self.assertIsNone(policy.choose(board(), "green", "invalid"))


if __name__ == "__main__":
    unittest.main()
