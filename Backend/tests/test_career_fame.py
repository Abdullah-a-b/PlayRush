"""اختبارات الشهرة ومعرفة البوت؛ لا حسابات أو اتصالات قاعدة بيانات."""
import ast
import inspect
import json
import random
import tempfile
import types
import unittest
from pathlib import Path
from unittest.mock import patch
from app.core import career_fame as fame, paths
from app.domains.games.career import solo_bot as bot

class FameTests(unittest.TestCase):
 def setUp(self):
  self.tmp=tempfile.TemporaryDirectory();self.root=Path(self.tmp.name);self.patch=patch.object(paths,'DATA_DIR',self.root);self.patch.start();self.save({})
 def tearDown(self):self.patch.stop();self.tmp.cleanup()
 def save(self,players):
  (self.root/'career_fame_review.json').write_text(json.dumps({'players':players}),encoding='utf-8')
 def test_unreviewed_is_pending_not_automatically_medium(self):
  r=fame.reviewed_classification('Q9999');self.assertFalse(r['eligible']);self.assertEqual(r['status'],'pending_review')
 def test_failed_or_missing_measurement_does_not_downgrade_known_anchor(self):
  self.save({'Q62786':dict(status='reviewed',fame='medium',career_memory='standard',evidence={'attention':{'status':'rate_limited','median_monthly':None}})})
  self.assertEqual(fame.reviewed_classification('Q62786','hard')['difficulty'],'medium')
 def test_review_reload_and_excluded_identity(self):
  self.save({'Q1':dict(status='reviewed',fame='easy')});self.assertEqual(fame.reviewed_classification('Q1')['difficulty'],'easy')
  self.save({'Q1':dict(status='excluded',fame=None)});self.assertFalse(fame.reviewed_classification('Q1')['eligible'])
 def test_missing_registry_is_not_treated_as_unknown_players(self):
  (self.root/'career_fame_review.json').unlink()
  with self.assertRaises(RuntimeError):fame.reviewed_classification('Q1','easy')
 def test_bad_review_fails_closed(self):
  self.save({'Q1':dict(status='reviewed',fame='famous')})
  with self.assertRaises(ValueError):fame.reviewed_classification('Q1')
 def test_probability_is_monotone_in_fame_and_bot_skill(self):
  for memory in ['standard','specialist']:
   for level in bot.DIFFICULTIES:
    values=[bot.knowledge_probability(level,t,memory) for t in ['hard','medium','easy']];self.assertEqual(values,sorted(values));self.assertTrue(all(0<x<1 for x in values))
   for tier in ['easy','medium','hard']:
    values=[bot.knowledge_probability(level,tier,memory) for level in ['beginner','medium','hard','expert']];self.assertEqual(values,sorted(values))
 def test_known_name_does_not_imply_known_old_playing_career(self):
  self.assertLess(bot.knowledge_probability('medium','easy','specialist'),bot.knowledge_probability('medium','easy','standard'))
 def test_hook_consumes_both_reviewed_dimensions(self):
  tree=ast.parse((Path(__file__).resolve().parents[1]/'app/domains/games/career/events.py').read_text(encoding='utf-8'));hook=next(n for n in ast.walk(tree) if isinstance(n,ast.FunctionDef) and n.name=='_bot_on_new_player');env={'_solo':bot};exec(compile(ast.Module(body=[hook],type_ignores=[]),'hook','exec'),env)
  for memory,expected in [('standard',True),('specialist',False)]:
   gs=types.SimpleNamespace(current_player={'difficulty':'easy','career_memory':memory},bot_difficulty='medium')
   with patch.object(bot.random,'random',return_value=.8):env['_bot_on_new_player'](gs)
   self.assertEqual(gs.bot_knows_current_player,expected)
 def test_prior_does_not_accept_hidden_club_information(self):
  self.assertEqual(list(inspect.signature(bot.knowledge_probability).parameters),['difficulty_name','player_difficulty','career_memory'])
 def test_committed_review_has_outside_top_five_anchor_and_no_automatic_geography_rule(self):
  data=json.loads((Path(__file__).resolve().parents[1]/'data/career_fame_review.json').read_text(encoding='utf-8'))['players']
  self.assertEqual(data['Q62786']['fame'],'medium');self.assertEqual(data['Q12897']['fame'],'easy')
  self.assertGreaterEqual(sum(p['status']=='reviewed' for p in data.values()),300)
if __name__=='__main__':unittest.main()
