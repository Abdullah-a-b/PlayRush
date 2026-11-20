import ast
import random
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock
import hmac
from jose import jwt, JWTError
from app.domains.games.knowledge.solo_bot import plan_turn


class MobileAndKnowledgeTests(unittest.TestCase):
    def test_resume_after_day_eight_and_revoke(self):
        source = Path(__file__).resolve().parents[1] / 'app/core/security.py'
        names = {'session_is_valid', 'mobile_resume_credential', 'resume_mobile_user'}
        nodes = [n for n in ast.parse(source.read_text('utf8')).body if getattr(n, 'name', '') in names]
        env = dict(jwt=jwt, JWTError=JWTError, SECRET_KEY='unit-test', ALGORITHM='HS256', User=object, hmac=hmac)
        exec(compile(ast.Module(body=nodes, type_ignores=[]), str(source), 'exec'), env)
        user = SimpleNamespace(id=2, session_token='initial-epoch', is_banned=False)
        db = Mock()
        db.get.return_value = user
        credential = env['mobile_resume_credential'](user)
        expired_access = jwt.encode({'sub':'example', 'exp':datetime.now(timezone.utc)-timedelta(days=1)}, 'unit-test')
        self.assertIsNone(env['resume_mobile_user'](db, expired_access))
        self.assertIs(env['resume_mobile_user'](db, credential), user)
        user.session_token = 'logged-out'
        self.assertIsNone(env['resume_mobile_user'](db, credential))

    def test_bot_can_repeat_guess_wrong_or_timeout_and_levels_differ(self):
        totals = []
        for level in ('beginner','medium','hard','expert'):
            rng = random.Random(91)
            outcomes = []
            for _ in range(1000):
                seconds, answer = plan_turn([{'display': v} for v in ('one','two','three')], {0,1}, level, rng, distractors=['four'])
                outcomes.append(answer)
                self.assertTrue(0 < seconds <= 10)
            self.assertEqual(set(outcomes), {None,"one","two","three","four"})
            totals.append(outcomes.count("three"))
        self.assertEqual(sorted(set(totals)), totals)
