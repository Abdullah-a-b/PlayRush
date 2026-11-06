"""فحص المساعدات المفعلة في الألعاب الخمس عبر المعالجات الفعلية."""
import asyncio, importlib, sys, time, types, unittest
from unittest.mock import patch
from test_game_integrity import functions
from app.core.huroof_answers import _core
from app.domains.games.reconnect import resolve_sid

class HelpHandlerTests(unittest.TestCase):
 def setup_case(self,game,hid,equipped=True,stock=True):
  mod=importlib.import_module('app.domains.games.'+game+'.engine')
  cls=getattr(mod,{'huroof':'HuroofGameState','career':'CareerGameState','bank':'BankGameState','whoami':'WhoamiGameState','knowledge':'KnowledgeGameState'}[game])
  players=[{'sid':'a','user_id':1,'name':'a'},{'sid':'b','user_id':2,'name':'b'}]
  gs=cls('a','b',players=players);gs.match_help_loadouts={'a':[hid] if equipped else []};gs.turn='a';gs.answer_deadline=time.time()+10
  if game=='career':
   gs.start_new_player({'id':1,'name':'محمد صلاح','clubs':[{'name':'نادي'}],'nationality':'مصرية','era':'2000-2026','position':'مهاجم'});gs.stage='buzzed' if hid=='c_extend_write' else 'revealing';gs.buzzed_player='a' if hid=='c_extend_write' else None
  if game=='whoami':
   gs.start_new_character({'id':'x','name':'اسم تجريبي','category':'علوم','era':'قرن','hints':['أ','ب','ج','د','هـ']});gs.stage='buzzed' if hid=='w_extend_buzz' else 'revealing';gs.buzzed_player='a' if hid=='w_extend_buzz' else None
  if game=='bank':
   gs.start_round();gs.pstate['a']['question']={'id':'q','q':'سؤال','a':'القاهرة','diff':'easy'};gs.pstate['a']['temp']=5
  if game=='knowledge':
   gs.stage='turn';gs.turn='a';gs.strikes['a']=2;gs.answers_pool=[{'display':'القاهرة','norm':{'القاهره'}}];gs.turn_started_at=time.time()
  if game=='huroof':
   gs.stage='selecting' if hid=='choose_category' else 'buzz_r1';gs.active_hex={'index':0,'letter':'ج'};gs.current_question={'id':1,'answer':'الجزائر','category':'جغرافيا'};gs.active_timer={'version':gs.state_version,'ends_at':time.time()+10,'timeout_type':'timeout_buzz_r1'}
  room={'state':'playing','game_state':gs,'players':players,'user_ids':{'a':1,'b':2}};calls=[];tasks=[];debits=[]
  class Sio:
   async def emit(self,e,d,**kw):calls.append((e,d))
   def start_background_task(self,f,*args):tasks.append((f,args))
  async def noop(*args,**kw):return None
  sio=Sio();env={'resolve_sid':resolve_sid,'get_room_state':lambda c:room,'_room_gs':lambda c:(room,gs),'sio':sio,'_sio_ref':sio,'time':time,'asyncio':types.SimpleNamespace(sleep=noop),'_answer_timeout':noop,'huroof_timer_task':noop,'trigger_new_question':noop,'_next_question':noop,'_begin_turn':noop,'_notify_opponent_help':noop,'_name_of':lambda r,s:s,'_safe_by_name':lambda r,g:{},'_load_huroof_questions_cached':lambda:[{'category':'جغرافيا'}],'hint_core':_core}
  functions(f'app/domains/games/{game}/events.py',{game+'_use_help'},env)
  core=types.ModuleType('app.domains.games.core_manager');core._allow_same_ip=lambda:False
  inv=types.ModuleType('app.domains.wallet.help_inventory')
  def consume(uid,help_id):debits.append(help_id);return stock
  inv.consume_help=consume;inv.get_quantity=lambda *a:1 if stock else 0
  ac=types.ModuleType('app.core.anticheat');ac.check_action_rate=lambda *a,**kw:None
  return gs,env,calls,tasks,debits,{'app.domains.games.core_manager':core,'app.domains.wallet.help_inventory':inv,'app.core.anticheat':ac}

 def run_case(self,game,hid,**options):
  gs,env,calls,tasks,debits,stubs=self.setup_case(game,hid,**options)
  with patch.dict(sys.modules,stubs):asyncio.run(env[game+'_use_help']('a',{'roomCode':'LOCAL','helpId':hid,'category':'جغرافيا'}))
  return gs,calls,tasks,debits

 def test_every_enabled_help_has_effect_and_one_debit(self):
  for game in ['huroof','career','bank','whoami','knowledge']:
   catalog=importlib.import_module('app.domains.games.'+game+'.helps')
   for h in catalog.get_enabled_catalog():
    with self.subTest(game=game,help=h['id']):
     gs,calls,tasks,debits=self.run_case(game,h['id'])
     self.assertTrue(any(e==game+'_help_result' and d.get('ok') for e,d in calls),calls)
     self.assertEqual(debits,[h['id']])
     self.assertIn(h['id'],gs.helps_used['a'])
     if h['id']=='w_extend_buzz':self.assertEqual(tasks[-1][1][1],gs.state_version)

 def test_unequipped_help_never_debits_or_applies(self):
  for game in ['huroof','career','bank','whoami','knowledge']:
   h=importlib.import_module('app.domains.games.'+game+'.helps').get_enabled_catalog()[0]
   with self.subTest(game=game):
    gs,calls,tasks,debits=self.run_case(game,h['id'],equipped=False)
    self.assertFalse(any(e==game+'_help_result' and d.get('ok') for e,d in calls));self.assertEqual(debits,[]);self.assertNotIn(h['id'],gs.helps_used['a'])

 def test_no_stock_never_applies_help(self):
  for game in ['huroof','career','bank','whoami','knowledge']:
   h=importlib.import_module('app.domains.games.'+game+'.helps').get_enabled_catalog()[0]
   with self.subTest(game=game):
    gs,calls,tasks,debits=self.run_case(game,h['id'],stock=False)
    self.assertFalse(any(e==game+'_help_result' and d.get('ok') for e,d in calls));self.assertNotIn(h['id'],gs.helps_used['a'])

 def test_help_cannot_be_used_twice(self):
  for game in ['huroof','career','bank','whoami','knowledge']:
   h=importlib.import_module('app.domains.games.'+game+'.helps').get_enabled_catalog()[0]
   gs,env,calls,tasks,debits,stubs=self.setup_case(game,h['id'])
   with patch.dict(sys.modules,stubs):
    asyncio.run(env[game+'_use_help']('a',{'roomCode':'LOCAL','helpId':h['id']}))
    asyncio.run(env[game+'_use_help']('a',{'roomCode':'LOCAL','helpId':h['id']}))
   self.assertEqual(len(debits),1,(game,debits))


 def test_non_player_cannot_use_any_help(self):
  for game in ['huroof','career','bank','whoami','knowledge']:
   h=importlib.import_module('app.domains.games.'+game+'.helps').get_enabled_catalog()[0]
   gs,env,calls,tasks,debits,stubs=self.setup_case(game,h['id'])
   with patch.dict(sys.modules,stubs):asyncio.run(env[game+'_use_help']('outsider',{'roomCode':'LOCAL','helpId':h['id']}))
   self.assertEqual(debits,[]);self.assertFalse(any(e==game+'_help_result' and d.get('ok') for e,d in calls))

 def test_missing_hint_and_category_picker_never_charge(self):
  for game,hid,field in [('career','c_era','era'),('whoami','w_reveal_era','era')]:
   gs,env,calls,tasks,debits,stubs=self.setup_case(game,hid)
   current=gs.current_player if game=='career' else gs.current;current[field]=None
   with patch.dict(sys.modules,stubs):asyncio.run(env[game+'_use_help']('a',{'roomCode':'LOCAL','helpId':hid}))
   self.assertEqual(debits,[]);self.assertNotIn(hid,gs.helps_used['a'])
  gs,env,calls,tasks,debits,stubs=self.setup_case('huroof','choose_category')
  with patch.dict(sys.modules,stubs):asyncio.run(env['huroof_use_help']('a',{'roomCode':'LOCAL','helpId':'choose_category'}))
  self.assertEqual(debits,[]);self.assertTrue(any(e=='huroof_choose_category_options' for e,d in calls))

 def test_time_extension_does_not_invalidate_its_new_timer(self):
  for game,hid in [('whoami','w_extend_buzz'),('knowledge','k_time_plus'),('career','c_extend_write')]:
   gs,calls,tasks,debits=self.run_case(game,hid)
   if game == 'knowledge':
    fired=[]
    async def strike(*args):fired.append(args)
    tasks[-1][0].__globals__['_apply_strike']=strike
    asyncio.run(tasks[-1][0]())
    self.assertEqual(len(fired),1)
   else:
    self.assertEqual(tasks[-1][1][1],gs.state_version)

if __name__=='__main__':unittest.main()
