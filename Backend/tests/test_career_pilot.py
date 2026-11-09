from collections import Counter
import unittest

from app.domains.games.career import pilot, solo_bot


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
            1002: ["الدعيع", "Mohamed Al-Deayea"],
            172: ["مبابي", "Kylian Mbappe"],
            219: ["دروجبا", "Didier Drogba"],
            205: ["تشافي", "Xavi Hernandez"],
            1006: ["أبو تريكة", "ابوتريكة"],
            1007: ["بيبو", "Mahmoud Al Khatib"],
            1009: ["القحطاني", "Yasser Al-Qahtani"],
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
            165: ["رونالدو البرازيلي", "رونالدو نازاريو", "Ronaldo Nazário", "CR8"],
            274: ["لويس", "لويس سواريز", "Luis"],
            205: ["هيرنانديز", "Javier Hernandez"],
            181: ["جيانلويجي دوناروما"],
        }
        for pid, answers in cases.items():
            for answer in [*answers, "", "ــّ", None, ["ميسي"], "ميسي" * 80]:
                with self.subTest(answer=answer):
                    self.assertFalse(pilot.accepts_name(answer, pilot.ROSTER[pid]))

    def test_deck_rotation_keeps_round_balance_and_uses_full_roster(self):
        first_five = set()
        self.assertGreaterEqual(len(pilot.ROSTER), 50)
        for _ in range(30):
            order = pilot.round_order()
            self.assertEqual(set(order), set(pilot.ROSTER))
            self.assertEqual(len(order), len(pilot.ROSTER))
            self.assertEqual(Counter(pilot.ROSTER[pid]["difficulty"] for pid in order[:5]),
                             {"easy": 2, "medium": 2, "hard": 1})
            first_five.update(order[:5])
        self.assertGreater(len(first_five), 15)

    def test_every_roster_sequence_keeps_its_player_until_the_end(self):
        self.assertEqual(pilot.matching_players([]), [])
        for player in pilot.ROSTER.values():
            clubs = player["clubs"]
            with self.subTest(name=player["name"]):
                self.assertTrue(player["sources"])
                self.assertIn(player["recognition"], {"easy", "medium", "hard"})
                self.assertLessEqual(1, player["anchor"])
                self.assertLessEqual(player["anchor"], len(clubs))
                for count in range(1, len(clubs) + 1):
                    self.assertIn(player, pilot.matching_players(clubs[:count]))
                self.assertIn(player, pilot.matching_players(clubs, complete=True))

    def test_shared_opening_and_public_completion(self):
        clues = [{"name": "برشلونة"}]
        self.assertEqual({p["id"] for p in pilot.matching_players(clues)}, {164, 189, 205, 284})
        self.assertEqual([p["id"] for p in pilot.matching_players(clues, complete=True)], [284])

    def test_bot_waits_or_guesses_a_plausible_name_and_is_stable(self):
        candidates = pilot.matching_players([{"name": "برشلونة"}])
        guesses = []
        for seed in range(120):
            decision = solo_bot.reviewed_decision("medium", candidates, 1, False, 0, seed, 10)
            self.assertEqual(decision, solo_bot.reviewed_decision("medium", candidates, 1, False, 0, seed, 10))
            if decision:
                guesses.append(decision)
                self.assertEqual(decision["answer"], pilot.ROSTER[284]["name"])
                self.assertTrue(1.5 <= decision["buzz_delay"] <= 3)
                self.assertTrue(0 < decision["answer_delay"] < 10)
        self.assertTrue(0 < len(guesses) < 60)

    def test_expert_knows_more_but_can_miss_a_round(self):
        candidates = [pilot.ROSTER[67]]
        def attempts(level):
            return sum(solo_bot.reviewed_decision(level, candidates, 5, True, 0, seed, 10) is not None
                       for seed in range(300))
        self.assertTrue(0 < attempts("beginner") < attempts("expert") < 300)
        self.assertIsNone(solo_bot.reviewed_decision("expert", candidates, 1, False, 0, 1, 10))
        self.assertIsNone(solo_bot.reviewed_decision("expert", candidates, 5, True, 2, 1, 10))

    def test_legend_exception_is_in_the_playable_roster(self):
        pele = pilot.ROSTER_BY_QID["Q34670"]
        self.assertEqual(pele["admission"], "legend_exception")
        self.assertIn(pele["id"], pilot.round_order())
        self.assertEqual([club["name"] for club in pele["clubs"]], ["سانتوس", "نيويورك كوسموس"])
        for alias in ("بيليه", "بيلي", "Pelé", "Pele"):
            self.assertTrue(pilot.accepts_name(alias, pele))


    def test_shared_ronaldo_alias_respects_the_current_round(self):
        cristiano = pilot.ROSTER_BY_QID["Q11571"]
        nazario = pilot.ROSTER_BY_QID["Q529207"]
        for player in (cristiano, nazario):
            for alias in ("رونالدو", "رونلدو", "Ronaldo"):
                self.assertTrue(pilot.accepts_name(alias, player))
        self.assertFalse(pilot.accepts_name("رونالدو البرازيلي", cristiano))
        self.assertFalse(pilot.accepts_name("كريستيانو رونالدو", nazario))
        self.assertTrue(pilot.accepts_name("Ronaldo Nazário", nazario))

    def test_reviewed_legend_admissions(self):
        exceptions = {p["wikidata_id"] for p in pilot.ROSTER.values() if p.get("admission") == "legend_exception"}
        self.assertTrue({"Q34670", "Q1799274", "Q981909", "Q1249859"} <= exceptions)
