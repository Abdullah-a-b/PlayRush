import unittest
from types import SimpleNamespace

from app.core.shadow_network import network_cases


def detect(results):
    rows = (SimpleNamespace(low_id=min(w, l), high_id=max(w, l), winner_id=w,
                            match_id=str(i), surrendered=s)
            for i, (w, l, s) in enumerate(results))
    return [reason for reason, _, _ in network_cases(rows)]


class NetworkReview(unittest.TestCase):
    def test_many_to_one(self):
        matches = [(1, r, True) for r in (2, 3, 4)] * 2
        self.assertIn("multiple_accounts_conceding_to_one", detect(matches))
        self.assertEqual(detect([(w, l, False) for w, l, _ in matches]), [])

    def test_cycle_without_surrenders(self):
        cycle = [(1, 2, False), (2, 3, False), (3, 1, False)] * 2
        self.assertEqual(detect(cycle), ["concentrated_circular_wins"])
        self.assertEqual(detect(cycle + [(2, 1, False)]), [])

    def test_selective_losses_require_outside_comparison(self):
        losses = [(1, 2, True)] * 2 + [(1, 2, False)] * 3
        self.assertEqual(detect(losses), [])
        self.assertIn("selective_losses_to_one_opponent", detect(losses + [(2, 3, False)] * 5))
