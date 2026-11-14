"""اختبارات عدالة ذاكرة البوت وفصل المستويات؛ بيانات اصطناعية بلا قاعدة بيانات."""
import ast
import asyncio
import json
from pathlib import Path
import random
import statistics
import time
import types
import unittest
from unittest.mock import AsyncMock, patch

from app.domains.games.huroof import solo_bot as bot
from app.domains.games.huroof import learned_policy
from app.domains.games.huroof.engine import HuroofGameState
from app.domains.games.solo_adaptation import adapt_reaction_delay, record_human_answer


def game(level="beginner", difficulty="rare", text="سؤال تجريبي أول"):
    state = HuroofGameState("human", bot.BOT_SID)
    state.is_solo = True
    state.bot_difficulty = level
    state.current_question = {
        "question": text, "difficulty": difficulty, "letter": "ج",
        "answer": "جواب تجريبي", "accepted_answers": [],
    }
    return state


class HuroofHumanPolicyTests(unittest.TestCase):
    def setUp(self):
        self.random_state = random.getstate()
        random.seed(20261113)

    def tearDown(self):
        random.setstate(self.random_state)

    def test_unknown_stays_unknown_across_retries_and_transfer(self):
        state = game()
        with patch.object(bot, "bot_knows_answer", return_value=False) as knowledge:
            first = bot.question_plan(state, 40)
            self.assertFalse(first["knows"])
            self.assertFalse(first["will_buzz"])
            knowledge.return_value = True
            for attempt, transfer in ((1, True), (2, False), (2, True)):
                plan = bot.question_plan(state, 12, attempt, transfer=transfer)
                self.assertFalse(plan["knows"])
                self.assertFalse(plan["will_buzz"])
            self.assertEqual(knowledge.call_count, 1)

    def test_new_question_with_same_answer_gets_new_knowledge(self):
        state = game()
        with patch.object(bot, "bot_knows_answer", side_effect=[False, True]) as knowledge:
            self.assertFalse(bot.question_plan(state, 40)["knows"])
            state.current_question = dict(state.current_question, question="سؤال تجريبي مختلف")
            self.assertTrue(bot.question_plan(state, 40)["knows"])
            self.assertEqual(knowledge.call_count, 2)

    def test_round_reset_does_not_reuse_previous_question_memory(self):
        for reset_name in ("reset_board", "reset_round_state"):
            with self.subTest(reset=reset_name):
                state = game()
                previous = dict(state.current_question)
                with patch.object(bot, "bot_knows_answer", side_effect=[False, True]) as knowledge:
                    self.assertFalse(bot.question_plan(state, 40)["knows"])
                    getattr(state, reset_name)()
                    state.current_question = previous
                    self.assertTrue(bot.question_plan(state, 40)["knows"])
                    self.assertEqual(knowledge.call_count, 2)

    def test_question_memory_survives_json_round_trip(self):
        state = game()
        with patch.object(bot, "bot_knows_answer", return_value=False) as knowledge:
            bot.question_plan(state, 40)
            restored = HuroofGameState.from_dict(json.loads(json.dumps(state.to_dict())))
            self.assertEqual(restored.bot_question_memory, state.bot_question_memory)
            self.assertEqual(restored.bot_difficulty, state.bot_difficulty)
            self.assertTrue(restored.is_solo)
            knowledge.return_value = True
            self.assertFalse(bot.question_plan(restored, 20, transfer=True)["knows"])
            self.assertEqual(knowledge.call_count, 1)

    def test_second_attempt_survives_json_round_trip(self):
        state = game()
        state.attempts = 2
        restored = HuroofGameState.from_dict(json.loads(json.dumps(state.to_dict())))
        self.assertEqual(restored.attempts, 2)

    def test_private_memory_does_not_mutate_question_payload(self):
        state = game()
        before = dict(state.current_question)
        bot.question_plan(state, 40)
        self.assertEqual(state.current_question, before)
        self.assertNotIn("bot_question_memory", state.current_question)

    def test_known_question_can_wait_without_losing_knowledge(self):
        state = game("expert", "easy")
        with patch.object(bot, "bot_knows_answer", return_value=True) as knowledge:
            plans = [bot.question_plan(state, 40, 1) for _ in range(40)]
            plans.append(bot.question_plan(state, 12, 2, transfer=True))
            self.assertTrue(all(plan["knows"] for plan in plans))
            self.assertEqual(knowledge.call_count, 1)

    def test_plans_stay_inside_short_answer_windows(self):
        with patch.object(bot, "bot_knows_answer", return_value=True):
            for level in bot.DIFFICULTIES:
                for window in (0.1, 1, 5, 12, 40):
                    for transfer in (False, True):
                        for index in range(30):
                            state = game(level, "hard", str(index))
                            plan = bot.question_plan(state, window, transfer=transfer)
                            if plan["delay"] is not None:
                                with self.subTest(level=level, window=window, transfer=transfer):
                                    self.assertGreaterEqual(plan["delay"], 0)
                                    self.assertLess(plan["delay"], window)

    def test_beginner_rare_and_hard_limits_hold_even_on_retry(self):
        samples = 20000
        for difficulty, upper in (("rare", .008), ("hard", .035)):
            for attempt in (1, 2):
                random.seed(9021)
                known = sum(bot.bot_knows_answer("beginner", difficulty, attempt)
                            for _ in range(samples)) / samples
                with self.subTest(difficulty=difficulty, attempt=attempt):
                    self.assertLess(known, upper)

    def test_four_levels_have_distinct_knowledge_and_thinking_time(self):
        rates, delays = [], []
        for level in bot.DIFFICULTIES:
            random.seed(61011)
            plans = [bot.decide_on_question(level, "medium", 40) for _ in range(12000)]
            buzzing = [p["delay"] for p in plans if p["will_buzz"]]
            rates.append(len(buzzing) / len(plans))
            delays.append(statistics.mean(buzzing))
        for easier, harder in zip(rates, rates[1:]):
            self.assertGreater(harder - easier, .08)
        for slower, faster in zip(delays, delays[1:]):
            self.assertGreater(slower - faster, .7)

    def test_expert_is_not_omniscient_on_rare_questions(self):
        random.seed(9147)
        rate = sum(bot.bot_knows_answer("expert", "rare") for _ in range(16000)) / 16000
        self.assertGreater(rate, .1)
        self.assertLess(rate, .27)

    def test_adaptation_changes_pace_inside_each_level_without_changing_knowledge(self):
        slow = {"is_solo": True}
        fast = {"is_solo": True}
        for _ in range(6):
            record_human_answer(slow, "human", bot.BOT_SID, False)
            record_human_answer(fast, "human", bot.BOT_SID, True, quick=True)
        for level, config in bot.DIFFICULTIES.items():
            minimum, maximum = config["buzz_min"], config["buzz_max"]
            center = (minimum + maximum) / 2
            quicker = adapt_reaction_delay(fast, center, minimum, maximum)
            slower = adapt_reaction_delay(slow, center, minimum, maximum)
            with self.subTest(level=level):
                self.assertLess(quicker, center)
                self.assertGreater(slower, center)
                self.assertGreaterEqual(quicker, minimum)
                self.assertLessEqual(slower, maximum)
                state = game(level)
                with patch.object(bot, "bot_knows_answer", return_value=False) as knowledge:
                    bot.question_plan(state, 40)
                    before = dict(state.bot_question_memory)
                    for room in (slow, fast):
                        for initial in (minimum, center, maximum):
                            adjusted = adapt_reaction_delay(room, initial, minimum, maximum)
                            self.assertGreaterEqual(adjusted, minimum)
                            self.assertLessEqual(adjusted, maximum)
                    knowledge.return_value = True
                    self.assertFalse(bot.question_plan(state, 30, 2)["knows"])
                    self.assertEqual(state.bot_question_memory, before)

    def test_bot_answers_do_not_teach_adaptation_about_human(self):
        room = {"is_solo": True}
        record_human_answer(room, bot.BOT_SID, bot.BOT_SID, True, quick=True)
        record_human_answer(room, None, bot.BOT_SID, True, quick=True)
        self.assertNotIn("solo_human_answers", room)

    def test_transfer_does_not_ask_model_to_supply_unknown_answer(self):
        """نفحص ربط الحدث نفسه: غياب المعرفة لا يعوضه مفتاح الإجابة أو الموديل."""
        path = Path(__file__).resolve().parents[1] / "app/domains/games/huroof/events.py"
        tree = ast.parse(path.read_text(encoding="utf-8-sig"))
        node = next(n for n in ast.walk(tree)
                    if isinstance(n, ast.AsyncFunctionDef) and n.name == "_bot_answer_transfer")
        state = game()
        state.buzzed_player = bot.BOT_SID
        state.stage = "answer_r2"
        room = {"state": "playing", "is_solo": True, "game_state": state}
        process, model, judge = AsyncMock(), AsyncMock(), AsyncMock()
        environment = {
            "get_room_state": lambda _: room, "_solo": bot, "time": time,
            "random": random, "asyncio": types.SimpleNamespace(sleep=AsyncMock()),
            "_trained_huroof_answer": model, "_judge_trained_huroof_answer": judge,
            "process_answer_result": process,
        }
        exec(compile(ast.Module(body=[node], type_ignores=[]), str(path), "exec"), environment)
        with patch.object(bot, "bot_knows_answer", return_value=False):
            asyncio.run(environment["_bot_answer_transfer"]("LOCAL", state.state_version, 20))
        model.assert_not_awaited()
        judge.assert_not_awaited()
        process.assert_awaited_once()
        self.assertFalse(process.await_args.args[1])
        self.assertNotEqual(process.await_args.args[2], state.current_question["answer"])

    def test_late_transfer_cannot_answer_replaced_question_with_same_answer(self):
        path = Path(__file__).resolve().parents[1] / "app/domains/games/huroof/events.py"
        tree = ast.parse(path.read_text(encoding="utf-8-sig"))
        node = next(n for n in ast.walk(tree)
                    if isinstance(n, ast.AsyncFunctionDef) and n.name == "_bot_answer_transfer")
        state = game()
        state.buzzed_player = bot.BOT_SID
        state.stage = "answer_r2"
        room = {"state": "playing", "is_solo": True, "game_state": state}
        process, judge = AsyncMock(), AsyncMock()

        async def delayed_model(*args):
            state.current_question = dict(state.current_question, question="سؤال ثان له نفس الجواب")
            return ("answer", state.current_question["answer"])

        environment = {
            "get_room_state": lambda _: room, "_solo": bot, "time": time,
            "random": random, "asyncio": types.SimpleNamespace(sleep=AsyncMock()),
            "_trained_huroof_answer": delayed_model, "_judge_trained_huroof_answer": judge,
            "process_answer_result": process,
        }
        exec(compile(ast.Module(body=[node], type_ignores=[]), str(path), "exec"), environment)
        with patch.object(bot, "bot_knows_answer", return_value=True):
            asyncio.run(environment["_bot_answer_transfer"]("LOCAL", state.state_version, 20))
        process.assert_not_awaited()
        judge.assert_not_awaited()

    def test_invalid_policy_json_falls_back_instead_of_stopping_bot(self):
        try:
            for raw in ("[]", "null", "42", "{}", "not json"):
                learned_policy.load_policy.cache_clear()
                with self.subTest(raw=raw), patch.object(Path, "read_text", return_value=raw):
                    self.assertIsNone(learned_policy.load_policy("reaction_policy_v5.json"))
        finally:
            learned_policy.load_policy.cache_clear()


if __name__ == "__main__":
    unittest.main()
