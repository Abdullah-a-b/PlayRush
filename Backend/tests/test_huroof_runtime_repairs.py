"""تشغيل انتقالات المصدر الفعلية بساعة معزولة؛ بلا مستخدمين أو شبكة أو .env."""
import ast
import asyncio
from collections import Counter
import json
from pathlib import Path
import random
import time
import types
import unittest
from unittest.mock import AsyncMock, patch

from app.domains.games.huroof.engine import HuroofGameState
from app.domains.games.huroof import solo_bot as bot
from app.domains.games.huroof.question_pool import choose_question
from app.domains.games.solo_adaptation import adapt_reaction_delay
from app.core.huroof_answers import answer_letter, check_answer

ROOT = Path(__file__).resolve().parents[1]


def actual_functions(names, env):
    tree = ast.parse((ROOT / 'app/domains/games/huroof/events.py').read_text(encoding='utf-8-sig'))
    nodes = [node for node in ast.walk(tree) if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef))
             and node.name in names]
    assert len(nodes) == len(names)
    for node in nodes:
        node.decorator_list = []
    exec(compile(ast.Module(body=nodes, type_ignores=[]), 'actual_huroof_events', 'exec'), env)
    return env


class Socket:
    def __init__(self):
        self.emit = AsyncMock()
        self.tasks = []

    def start_background_task(self, function, *args):
        self.tasks.append((function, args))


def harness(solo=False):
    gs = HuroofGameState('human', bot.BOT_SID if solo else 'other')
    gs.is_solo, gs.bot_difficulty = solo, 'beginner'
    gs.active_hex = gs.board[0]
    gs.current_question = dict(question='حيوان يموء', answer='قط', accepted_answers=[],
                               letter='ق', difficulty='easy')
    gs.stage = 'answer_r2'
    gs.buzzed_player = gs.p2
    room = {'state': 'playing', 'game_state': gs, 'is_solo': solo}
    sio = Socket()
    sleep = AsyncMock()
    env = dict(get_room_state=lambda _: room, sio=sio, asyncio=types.SimpleNamespace(sleep=sleep),
               time=time, _SOLO_HOOKS={'consider_buzz': AsyncMock(), 'on_transfer': AsyncMock()},
               trigger_new_question=AsyncMock(), _solo=bot, record_human_answer=lambda *a, **k: None)
    actual_functions({'advance_state', 'huroof_timer_task', 'enter_last_chance',
                      'finish_unanswered_question', 'process_answer_result'}, env)
    return gs, room, sio, sleep, env


class HuroofTimerRepairs(unittest.IsolatedAsyncioTestCase):
    async def test_wrong_second_answer_schedules_real_last_chance_and_replaces_question(self):
        for solo in (False, True):
            with self.subTest(solo=solo):
                gs, room, sio, sleep, env = harness(solo)
                await env['process_answer_result']('room', False, 'خطأ')
                timers = [(fn, args) for fn, args in sio.tasks if fn is env['huroof_timer_task']]
                self.assertEqual(len(timers), 1)
                fn, args = timers[0]
                self.assertEqual(args[2:], (30, 'timeout_buzz_r3'))
                self.assertEqual(gs.attempts, 2)
                self.assertIsNone(gs.buzzed_player)
                await fn(*args)
                self.assertEqual(gs.stage, 'revealing')
                env['trigger_new_question'].assert_awaited_once_with('room', is_change=True)

    async def test_both_timeout_entrances_schedule_last_chance(self):
        for kind in ('timeout_buzz_r1', 'timeout_answer_r2'):
            gs, room, sio, sleep, env = harness(True)
            await env['huroof_timer_task']('room', gs.state_version, 0, kind)
            timers = [args for fn, args in sio.tasks if fn is env['huroof_timer_task']]
            self.assertEqual(timers[0][2:], (30, 'timeout_buzz_r3'))
            self.assertTrue(any(fn is env['_SOLO_HOOKS']['consider_buzz'] for fn, _ in sio.tasks))

    async def test_timer_cancelled_by_buzz_cannot_replace_or_overwrite_current_timer(self):
        gs, room, sio, sleep, env = harness()
        gs.active_timer = {'version': gs.state_version, 'ends_at': 12345}
        old = dict(gs.active_timer)
        await env['huroof_timer_task']('room', gs.state_version - 1, 0, 'timeout_buzz_r3')
        self.assertEqual(gs.active_timer, old)
        sleep.assert_not_awaited()
        env['trigger_new_question'].assert_not_awaited()

    async def test_question_is_claimed_before_reveal_and_stale_reveal_does_not_replace(self):
        gs, room, sio, sleep, env = harness()
        async def during_reveal(seconds):
            self.assertEqual(gs.stage, 'revealing')
            gs.state_version += 1
            gs.current_question = {'question': 'سؤال أحدث'}
        sleep.side_effect = during_reveal
        await env['finish_unanswered_question']('room', gs)
        env['trigger_new_question'].assert_not_awaited()

    async def test_leaving_room_during_reveal_stops_replacement(self):
        gs, room, sio, sleep, env = harness()
        async def leave(_): room['state'] = 'finished'
        sleep.side_effect = leave
        await env['finish_unanswered_question']('room', gs)
        env['trigger_new_question'].assert_not_awaited()


def pool_row(idx, category='حيوانات', difficulty='easy', answer=None):
    return {'id': idx, 'category': category, 'difficulty': difficulty,
            'question_text': f'سؤال رقم {idx}', 'correct_answer': answer or f'قيمة{idx}',
            'valid_letters': {'ق'}, 'chemistry': category == 'كيمياء'}


class HuroofPoolRepairs(unittest.TestCase):
    def test_beginner_seen_easy_is_preferred_over_unseen_impossible(self):
        rows = [pool_row(1), pool_row(2, 'كيمياء', 'rare'), pool_row(3, 'جغرافيا', 'hard')]
        self.assertEqual(choose_question(rows, 'ق', seen_ids=[1], level='beginner')['id'], 1)

    def test_categories_are_not_weighted_by_table_size(self):
        rows = [pool_row(i, 'جغرافيا') for i in range(500)] + [pool_row(999, 'رياضة')]
        rng = random.Random(6511)
        sports = sum(choose_question(rows, 'ق', rng=rng)['category'] == 'رياضة' for _ in range(1000))
        self.assertTrue(400 < sports < 600, sports)

    def test_recent_geography_and_chemistry_yield_to_other_categories(self):
        rows = [pool_row(1, 'جغرافيا'), pool_row(2, 'كيمياء'), pool_row(3, 'رياضة')]
        self.assertEqual(choose_question(rows, 'ق', used_ids=[1, 2])['id'], 3)

    def test_used_and_seen_questions_and_same_answers_are_avoided(self):
        rows = [pool_row(i) for i in range(1, 5)]
        self.assertEqual(choose_question(rows, 'ق', used_ids=[1], seen_ids=[2],
                                         used_answers=[rows[2]['correct_answer']])['id'], 4)

    def test_no_ineligible_question_or_wrong_letter_fallback(self):
        self.assertIsNone(choose_question([pool_row(1, difficulty='rare')], 'ق'))
        self.assertIsNone(choose_question([pool_row(1)], 'س'))

    def test_user_category_preference_respects_level(self):
        rows = [pool_row(1, 'رياضة'), pool_row(2, 'أدب'), pool_row(3, 'كيمياء', 'rare')]
        self.assertEqual(choose_question(rows, 'ق', preferred_category='أدب')['id'], 2)
        self.assertNotEqual(choose_question(rows, 'ق', level='beginner', preferred_category='كيمياء')['id'], 3)

    def test_starter_bank_has_every_letter_and_answers_match(self):
        items = json.loads((ROOT / 'data/huroof_starter_questions.json').read_text(encoding='utf-8'))['questions']
        counts = Counter(answer_letter(item['a']) for item in items)
        self.assertEqual(len(counts), 28)
        self.assertGreaterEqual(min(counts.values()), 6)
        self.assertGreaterEqual(len({item['cat'] for item in items}), 10)
        for item in items:
            letter = answer_letter(item['a'])
            self.assertEqual(check_answer(item['a'], item['a'], item.get('accepted_answers', []), letter)['verdict'], 'accept', item)
            for alias in item.get('accepted_answers', []):
                self.assertEqual(check_answer(alias, item['a'], item['accepted_answers'], letter)['verdict'], 'accept', item)


class HuroofBotRuntime(unittest.IsolatedAsyncioTestCase):
    async def test_known_question_runs_think_buzz_answer_on_each_level_without_remote_model(self):
        for level in bot.DIFFICULTIES:
            with self.subTest(level=level):
                gs, room, sio, sleep, env = harness(True)
                gs.bot_difficulty, gs.stage, gs.buzzed_player = level, 'buzz_r1', None
                gs.attempts = 1
                judge = AsyncMock()
                trained = types.SimpleNamespace(decide=AsyncMock(return_value=None))
                env.update(random=random, trained_bot=trained, adapt_reaction_delay=adapt_reaction_delay,
                           _trained_huroof_answer=AsyncMock(return_value=None),
                           _judge_trained_huroof_answer=AsyncMock(), process_answer_result=judge)
                actual_functions({'_bot_consider_buzz'}, env)
                with patch.object(bot, 'bot_knows_answer', return_value=True), patch.object(bot.random, 'random', return_value=.99):
                    await env['_bot_consider_buzz']('room', gs.state_version, 40)
                self.assertTrue(any(call.args[0] == 'huroof_buzzed' for call in sio.emit.await_args_list))
                judge.assert_awaited_once_with('room', True, 'قط')
                self.assertGreaterEqual(sleep.await_args_list[0].args[0], bot.get_difficulty(level)['buzz_min'] - .1)

    async def test_unknown_stays_quiet_but_does_not_disable_later_known_question(self):
        gs, room, sio, sleep, env = harness(True)
        gs.stage, gs.buzzed_player, gs.attempts = 'buzz_r1', None, 1
        judge = AsyncMock()
        env.update(random=random, trained_bot=types.SimpleNamespace(decide=AsyncMock(return_value=None)),
                   adapt_reaction_delay=adapt_reaction_delay, _trained_huroof_answer=AsyncMock(),
                   _judge_trained_huroof_answer=AsyncMock(), process_answer_result=judge)
        actual_functions({'_bot_consider_buzz'}, env)
        with patch.object(bot, 'bot_knows_answer', return_value=False):
            await env['_bot_consider_buzz']('room', gs.state_version, 40)
        judge.assert_not_awaited()
        gs.current_question = dict(gs.current_question, question='سؤال بسيط جديد')
        gs.state_version += 1
        with patch.object(bot, 'bot_knows_answer', return_value=True), patch.object(bot.random, 'random', return_value=.99):
            await env['_bot_consider_buzz']('room', gs.state_version, 40)
        judge.assert_awaited_once()

    async def test_bot_does_not_buzz_after_human_wins_the_race(self):
        gs, room, sio, sleep, env = harness(True)
        gs.stage, gs.buzzed_player, gs.attempts = 'buzz_r1', None, 1
        async def human_buzz(_):
            gs.state_version += 1
            gs.buzzed_player = 'human'
        sleep.side_effect = human_buzz
        judge = AsyncMock()
        env.update(random=random, trained_bot=types.SimpleNamespace(decide=AsyncMock(return_value=None)),
                   adapt_reaction_delay=adapt_reaction_delay, process_answer_result=judge)
        actual_functions({'_bot_consider_buzz'}, env)
        with patch.object(bot, 'bot_knows_answer', return_value=True), patch.object(bot.random, 'random', return_value=.99):
            await env['_bot_consider_buzz']('room', gs.state_version, 40)
        judge.assert_not_awaited()
        self.assertEqual(gs.buzzed_player, 'human')
