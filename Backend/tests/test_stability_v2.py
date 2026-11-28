import os
import time
import unittest
import uuid
from concurrent.futures import ThreadPoolExecutor
from unittest.mock import patch

from app.domains.games.core_manager import candidate_pairs


class QueueBoundaries(unittest.TestCase):
    def test_older_wait_opens_class_but_never_bypasses_blocks(self):
        for threshold, shared_ip, previous, friends in [(0,False,False,False),(5,False,True,False),
                (10,True,False,False),(15,True,True,False),(20,False,False,True)]:
            a = dict(user_id=1,time=100,ip='x')
            b = dict(user_id=2,time=100+threshold,ip='x' if shared_ip else 'y')
            args = ({(1,2)} if friends else set(), {(1,2)} if previous else set())
            self.assertEqual(candidate_pairs([a,b],set(),*args,b['time']),[(0,1)])
            if threshold:
                self.assertEqual(candidate_pairs([a,b],set(),*args,b['time']-.01),[])
            self.assertEqual(candidate_pairs([a,b],{(1,2)},*args,b['time']),[])
            self.assertEqual(candidate_pairs([a,b],set(),*args,130),[])

    def test_first_entry_does_not_hold_others(self):
        entries=[dict(time=0,user_id=i,ip=str(i)) for i in (1,2,3)]
        self.assertEqual(candidate_pairs(entries,{(1,2),(1,3)},set(),set(),1),[(1,2)])



class ShadowPlayTests(unittest.TestCase):
    def test_flags_patterns_but_not_regular_rematches(self):
        from app.core.shadow_play import review_reason
        self.assertIsNone(review_reason([(1, False)] * 5))
        self.assertIsNone(review_reason([(1, True)] * 4))
        self.assertIsNone(review_reason([(1, True)] * 4 + [(None, False)]))
        self.assertEqual(review_reason([(1, True)] * 5), "five_same_winner_with_repeated_surrenders")
        self.assertEqual(review_reason([(i % 2, True) for i in range(5)]),
                         "five_alternating_winners_with_repeated_surrenders")

    def test_new_players_can_match_immediately(self):
        players = [dict(user_id=i, time=100, ip=str(i)) for i in (1, 2)]
        self.assertEqual(candidate_pairs(players, set(), set(), set(), 100), [(0, 1)])

class MigratedQuizContent(unittest.TestCase):
    def test_change_or_disablement_invalidates_grandfathered_entry(self):
        import json
        from app.core.paths import DATA_DIR
        from app.domains.games.ranked_content import eligible, fingerprint
        for mode in ("bank","knowledge"):
            raw = json.loads((DATA_DIR/(mode+"_questions.json")).read_text(encoding="utf8"))
            row = (raw["questions"] if isinstance(raw,dict) else raw)[0]
            self.assertTrue(eligible(row,mode))
            self.assertFalse(eligible(dict(row,active=False),mode))
            edited = dict(row,q=row["q"]+" updated")
            self.assertFalse(eligible(edited,mode))
            approved = dict(edited,ranked_approved=True,reviewed_hash=fingerprint(edited),
                            reviewed_at="2026-11-28",source="test editorial review")
            self.assertTrue(eligible(approved,mode))
