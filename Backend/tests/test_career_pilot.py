import unittest

from app.domains.games.career import pilot


class CareerPilotTests(unittest.TestCase):
    def test_reviewed_spellings(self):
        cases = {
            67: ["روي كُوستة", "Rui Costa"],
            164: ["ليـونل ميسي", "  LIONEL   MESSI!  ", "مِیسي"],
            165: ["CR٧", "CR۷", "كرستيانو رونالدو"],
            189: ["أندريس إنيستا", "Andrés Iniesta"],
            245: ["فيليب لاهم", "Philipp Lahm"],
            274: ["لويس فيجو", "Luis Figo"],
            293: ["ويسلي شنايدر", "Wesley Sneijder"],
        }
        for pid, spellings in cases.items():
            for spelling in spellings:
                with self.subTest(spelling=spelling):
                    self.assertTrue(pilot.accepts_name(spelling, pilot.ROSTER[pid]))
                    self.assertFalse(any(
                        pilot.accepts_name(spelling, other)
                        for other_id, other in pilot.ROSTER.items() if other_id != pid
                    ))

    def test_ambiguous_and_near_misses(self):
        cases = {
            67: ["كوستا", "دييغو كوستا", "Costa"],
            164: ["ليونيل", "ميسي ولا رونالدو", "Lionel Massi"],
            165: ["رونالدو", "Ronaldo", "رونالدو البرازيلي", "CR8"],
            274: ["لويس", "لويس سواريز", "Luis"],
        }
        for pid, answers in cases.items():
            for answer in [*answers, "", "ــّ", None, ["ميسي"], "ميسي" * 80]:
                with self.subTest(answer=answer):
                    self.assertFalse(pilot.accepts_name(answer, pilot.ROSTER[pid]))

    def test_order_and_bot_anchor(self):
        order = pilot.round_order()
        self.assertEqual(set(order), set(pilot.ROSTER))
        self.assertEqual(len(order), 7)
        self.assertEqual([pilot.ROSTER[pid]["difficulty"] for pid in order[:5]],
                         ["easy", "easy", "medium", "medium", "hard"])
        self.assertIsNone(pilot.candidate_from_clubs([]))
        for player in pilot.ROSTER.values():
            clubs, anchor = player["clubs"], player["anchor"]
            for count in range(1, anchor):
                self.assertIsNone(pilot.candidate_from_clubs(clubs[:count]))
            self.assertEqual(pilot.candidate_from_clubs(clubs[:anchor])["id"], player["id"])
