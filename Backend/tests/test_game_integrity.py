"""اختبارات أخطاء التدقيق على دوال المصدر الفعلية ببيانات معزولة."""
import ast, asyncio, datetime, importlib, json, time, types, unittest
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from unittest.mock import patch, MagicMock
from jose import jwt
from app.core.text_processor import check_answer, normalize_arabic
from app.domains.games.reconnect import remap_match_sid, resolve_sid
from app.domains.games.help_policy import help_denial
ROOT=Path(__file__).resolve().parents[1]


def functions(rel, names, env):
    tree=ast.parse((ROOT/rel).read_text(encoding='utf-8-sig'))
    nodes=[n for n in ast.walk(tree) if isinstance(n,(ast.FunctionDef,ast.AsyncFunctionDef)) and n.name in names]
    for n in nodes:n.decorator_list=[]
    exec(compile(ast.Module(body=nodes,type_ignores=[]),rel,'exec'),env)
    return env


class IntegrityTests(unittest.TestCase):
    def test_incomplete_names_and_distinct_entities_rejected(self):
        for typed,correct in [('محمد','محمد صلاح'),('محمد','محمد علي'),('غينيا','غينيا بيساو'),('جمهورية','جمهورية الكونغو الديمقراطية'),('النحل','النمل')]:
            with self.subTest(typed=typed,correct=correct):self.assertEqual(check_answer(typed,correct,[],None)['verdict'],'reject')
        self.assertEqual(check_answer('محمّد صلاح','محمد صلاح',[],None)['verdict'],'accept')
        self.assertEqual(check_answer('صلاح','محمد صلاح',['صلاح'],None)['verdict'],'accept')

    def test_ai_failure_negative_output_and_timeout_fail_closed(self):
        async def exercise():
            with ThreadPoolExecutor(max_workers=2) as pool:
                env=functions('app/infrastructure/ai_judge.py',{'judge_answer'},{'asyncio':asyncio,'_JUDGE_EXECUTOR':pool,'_get_model':lambda:None,'_JUDGE_PROMPT':'{question} {correct} {player}'})
                self.assertFalse((await env['judge_answer']('q','a','x'))['accept'])
                class Model:
                    def generate_content(self,p):return types.SimpleNamespace(text='لا، غير صحيح')
                env['_get_model']=lambda:Model();self.assertFalse((await env['judge_answer']('q','a','x'))['accept'])
                def slow():time.sleep(.08);return Model()
                env['_get_model']=slow;t=time.perf_counter();result=await env['judge_answer']('q','a','x',timeout=.005)
                self.assertEqual(result['source'],'timeout');self.assertLess(time.perf_counter()-t,.06)
        asyncio.run(exercise())

    def test_numeric_answers_preserve_meaning(self):
        f=functions('app/domains/games/bank/events.py',{'_normalize_digits'},{})['_normalize_digits']
        self.assertEqual(f('٧٥'),'75')
        for value in ['7.5','-75','75 cats','75 or 80']:self.assertEqual(f(value),'')

    def test_helper_metadata_does_not_cancel_running_timer(self):
        from app.domains.games.whoami.engine import WhoamiGameState
        from app.domains.games.knowledge.engine import KnowledgeGameState
        for cls in [WhoamiGameState,KnowledgeGameState]:
            gs=cls('a','b');v=gs.state_version;gs.mark_help_used('a','hint');self.assertEqual(gs.state_version,v)
        gs=WhoamiGameState('a','b');v=gs.state_version;gs.lock_points_for('a');self.assertEqual(gs.state_version,v)

    def test_fourth_slot_requires_purchase_and_level_for_every_game(self):
        for game in ['huroof','career','bank','whoami','knowledge']:
            h=importlib.import_module('app.domains.games.'+game+'.helps')
            with self.subTest(game=game):
                self.assertEqual(h.get_slots_for_player(9,True),3)
                self.assertEqual(h.get_slots_for_player(10,False),3)
                self.assertEqual(h.get_slots_for_player(10,True),4)

    def test_sid_remap_preserves_scores_inventory_and_timer_version(self):
        from app.domains.games.career.engine import CareerGameState
        from app.domains.games.bank.engine import BankGameState
        from app.domains.games.whoami.engine import WhoamiGameState
        from app.domains.games.knowledge.engine import KnowledgeGameState
        from app.domains.games.huroof.engine import HuroofGameState
        for cls in [CareerGameState,BankGameState,WhoamiGameState,KnowledgeGameState,HuroofGameState]:
            gs=cls('old','b',players=[{'sid':'old'},{'sid':'b'}]);gs.buzzed_player='old';gs.match_help_loadouts={'old':['test']};v=gs.state_version
            gs.scores={'old':7,'b':3};room={'host':'old','game_state':gs,'user_ids':{'old':1}}
            remap_match_sid(room,'old','new');self.assertEqual(gs.scores['new'],7);self.assertEqual(gs.buzzed_player,'new');self.assertEqual(gs.state_version,v)
            self.assertEqual(gs.match_help_loadouts['new'],['test']);self.assertEqual(resolve_sid(room,'old'),'new')
            remap_match_sid(room,'new','newer');self.assertEqual(resolve_sid(room,'old'),'newer')

    def test_guest_name_does_not_reconnect_as_host(self):
        e=functions('app/domains/games/core_manager.py',{'create_room','join_room'},{'rooms':{},'time':time})
        room=e['create_room']('LOCAL','host','Name',2,'career','local','','private');room['state']='playing'
        self.assertFalse(e['join_room']('LOCAL','attacker','Name','',None)[0]);self.assertEqual(room['players'][0]['sid'],'host')
        room['players'][0]['user_id']=1;self.assertTrue(e['join_room']('LOCAL','legitimate','Name','',1)[0])

    def test_session_rotation_invalidates_old_and_legacy_tokens(self):
        e=functions('app/core/security.py',{'session_is_valid','issue_user_token','revoke_user_sessions','create_access_token'},
                    {'jwt':jwt,'datetime':datetime.datetime,'timedelta':datetime.timedelta,'timezone':datetime.timezone,'SECRET_KEY':'test-key-for-isolated-tests-only','ALGORITHM':'HS256','ACCESS_TOKEN_EXPIRE_MINUTES':5,'secrets':__import__('secrets'),'hmac':__import__('hmac')})
        u=types.SimpleNamespace(email='synthetic@example.invalid',session_token=None)
        self.assertTrue(e['session_is_valid'](u,{'sub':u.email}))
        token=e['issue_user_token'](u);payload=jwt.decode(token,e['SECRET_KEY'],algorithms=['HS256']);self.assertTrue(e['session_is_valid'](u,payload))
        e['revoke_user_sessions'](u);self.assertFalse(e['session_is_valid'](u,payload));self.assertFalse(e['session_is_valid'](u,{'sub':u.email}))
        new=jwt.decode(e['issue_user_token'](u),e['SECRET_KEY'],algorithms=['HS256']);self.assertTrue(e['session_is_valid'](u,new))

    def test_career_shield_and_lock_expire_with_character(self):
        from app.domains.games.career.engine import CareerGameState
        gs=CareerGameState('a','b');gs.shields={'a':True};gs.double_locks={'a':True};gs.start_new_player({'id':1,'clubs':[{'name':'x'}]})
        self.assertEqual(gs.shields,{});self.assertEqual(gs.double_locks,{})

    def test_article_forms_preserve_proper_name_initials(self):
        from app.domains.games.knowledge.engine import KnowledgeGameState
        from app.core.huroof_answers import _forms
        gs=KnowledgeGameState('a','b');gs.answers_pool=[{'display':'ألبانيا','norm':_forms('ألبانيا')}]
        self.assertEqual(gs.match_answer(normalize_arabic('ألبانيا'))[0],'correct')
        self.assertEqual(gs.match_answer(normalize_arabic('بانيا'))[0],'none')
        gs.answers_pool=[{'display':'الجزائر','norm':_forms('الجزائر')}]
        self.assertEqual(gs.match_answer(normalize_arabic('جزائر'))[0],'correct')

    def test_no_fuzzy_country_substitution_in_knowledge_handler(self):
        from app.domains.games.knowledge.engine import KnowledgeGameState
        async def exercise():
            gs=KnowledgeGameState('a','b',players=[{'sid':'a'},{'sid':'b'}]);gs.stage='turn';gs.turn='a';gs.answers_pool=[{'display':'ألمانيا','norm':{normalize_arabic('ألمانيا')}}]
            room={'game_state':gs,'players':[{'sid':'a','user_id':1},{'sid':'b','user_id':2}]};out=[]
            async def correct(*a):out.append('correct')
            async def strike(*a):out.append('strike')
            env=functions('app/domains/games/knowledge/events.py',{'knowledge_submit_answer'},{'_room_gs':lambda c:(room,gs),'_norm':normalize_arabic,'_on_correct':correct,'_apply_strike':strike})
            await env['knowledge_submit_answer']('a',{'roomCode':'LOCAL','answer':'ألبانيا'});self.assertEqual(out,['strike']);self.assertEqual(gs.used_answer_idx,set())
        asyncio.run(exercise())

    def test_concurrent_answers_are_claimed_once(self):
        from app.domains.games.career.engine import CareerGameState
        from app.domains.games.whoami.engine import WhoamiGameState
        async def exercise(game,cls):
            gs=cls('a','b');gs.stage='buzzed';gs.buzzed_player='a';current={'name':'محمد صلاح','accepted_answers':[],'clubs':[],'hints':['x']}
            if game=='career':gs.current_player=current
            else:gs.current=current
            room={'state':'playing','game_state':gs};out=[]
            class Sio:
                async def emit(self,*a,**k):await asyncio.sleep(0)
            async def record(*a,**kw):out.append(a);await asyncio.sleep(0)
            env=functions(f'app/domains/games/{game}/events.py',{game+'_submit_answer'},{'get_room_state':lambda c:room,'sio':Sio(),'check_answer':check_answer,'_process_answer_result':record,'_handle_strike':record,'_resolve_end':record,'_start_character':record,'asyncio':types.SimpleNamespace(sleep=lambda t:asyncio.sleep(0))})
            await asyncio.gather(*[env[game+'_submit_answer']('a',{'roomCode':'LOCAL','answer':'محمد صلاح'}) for _ in range(2)])
            self.assertEqual(len(out),1)
            if game=='whoami':self.assertEqual(gs.scores['a'],4)
        for game,cls in [('career',CareerGameState),('whoami',WhoamiGameState)]:asyncio.run(exercise(game,cls))


    def test_huroof_same_attempt_is_not_processed_twice(self):
        from app.domains.games.huroof.engine import HuroofGameState
        async def exercise():
            gs=HuroofGameState('a','b');gs.stage='answer_r1';gs.buzzed_player='a';gs.current_question={'answer':'باريس','accepted_answers':[],'letter':'ب'};gs.active_hex={'index':0}
            room={'game_state':gs};out=[]
            async def process(*args):out.append(args);await asyncio.sleep(0)
            env=functions('app/domains/games/huroof/events.py',{'huroof_submit_answer'},{'check_payload_safety':lambda d:None,'check_action_rate':lambda *a,**k:None,'is_temp_banned':lambda s:False,'html':__import__('html'),'validate_huroof_answer':lambda *a:None,'get_room_state':lambda c:room,'check_answer':check_answer,'process_answer_result':process})
            await asyncio.gather(*[env['huroof_submit_answer']('a',{'roomCode':'LOCAL','answer':'باريس'}) for _ in range(2)])
            self.assertEqual(len(out),1)
        asyncio.run(exercise())

    def test_oauth_state_requires_cookie_signature_and_purpose(self):
        from fastapi import HTTPException
        e=functions('app/domains/users/service.py',{'make_google_state','validate_google_state'},{'secrets':__import__('secrets'),'datetime':datetime,'jwt':jwt,'JWTError':__import__('jose').JWTError,'SECRET_KEY':'isolated-test-key-32-characters-long','ALGORITHM':'HS256','HTTPException':HTTPException})
        state,nonce=e['make_google_state']('app');self.assertEqual(e['validate_google_state'](state,nonce),'app')
        for token,cookie in [(state,None),(state,'wrong'),(state+'x',nonce)]:
            with self.assertRaises(HTTPException):e['validate_google_state'](token,cookie)
        wrong=jwt.encode({'purpose':'other','nonce':nonce,'client':'app'},e['SECRET_KEY'],algorithm='HS256')
        with self.assertRaises(HTTPException):e['validate_google_state'](wrong,nonce)

    def test_bank_second_chance_timeout_uses_extended_window(self):
        async def exercise():
            gs=types.SimpleNamespace(ANSWER_WINDOW=8,stage='playing',round=1,pstate={'a':{'answering':True,'question':{'id':'q'}}});room={'game_state':gs};waits=[];handled=[]
            async def sleep(t):waits.append(t)
            async def handle(*args,**kwargs):handled.append(args)
            env=functions('app/domains/games/bank/events.py',{'_answer_timeout'},{'_room_gs':lambda c:(room,gs),'resolve_sid':resolve_sid,'asyncio':types.SimpleNamespace(sleep=sleep),'_handle_answer':handle})
            await env['_answer_timeout']('LOCAL','a','q',1,13);self.assertEqual(waits,[13]);self.assertEqual(len(handled),1)
        asyncio.run(exercise())

    def test_beginner_career_gives_player_first_clue_and_keeps_reaction_delay(self):
        from app.domains.games.career import solo_bot
        from app.domains.games.career.engine import CareerGameState

        async def exercise():
            gs = CareerGameState('human', solo_bot.BOT_SID)
            gs.is_solo = True
            gs.bot_difficulty = 'beginner'
            gs.start_new_player({'id': 1, 'clubs': [{'name': 'A'}, {'name': 'B'}]})
            room = {'game_state': gs, 'career_pilot_order': [1], 'career_bot_seed': 'test'}
            clock = [0.0]
            buzzes = []

            async def decide(*args, **kwargs):
                clock[0] += 2.4
                return ('buzz', 'Player')

            async def sleep(seconds):
                clock[0] += seconds

            async def buzz(*args):
                buzzes.append(clock[0])

            env = functions('app/domains/games/career/events.py', {'_bot_consider_buzz'}, {
                'get_room_state': lambda code: room, '_solo': solo_bot,
                'trained_bot': types.SimpleNamespace(decide=decide), '_EXPERT_PREVIEW': False,
                'adapt_reaction_delay': lambda room, delay, minimum, maximum: delay,
                'time': types.SimpleNamespace(monotonic=lambda: clock[0]),
                'random': types.SimpleNamespace(uniform=lambda low, high: low),
                'asyncio': types.SimpleNamespace(sleep=sleep), 'career_buzz': buzz,
            })
            consider = env['_bot_consider_buzz']
            await consider('LOCAL', gs.state_version, 5)
            self.assertEqual(clock[0], 0)
            gs.reveal_next_club()
            await consider('LOCAL', gs.state_version, 3)
            self.assertEqual(clock[0], 0)
            await consider('LOCAL', gs.state_version, 10)
            self.assertEqual(buzzes, [3.2])

        asyncio.run(exercise())

    def test_career_timer_survives_connection_remap_and_reveals_next_club(self):
        from app.domains.games.career.engine import CareerGameState
        async def exercise():
            gs=CareerGameState('old','b');gs.start_new_player({'id':1,'clubs':[{'name':'a'},{'name':'b'},{'name':'c'}]});room={'state':'playing','game_state':gs};calls=[]
            async def sleep(t):
                calls.append(t)
                if len(calls)==1:remap_match_sid(room,'old','new')
                else:gs.stage='finished'
            async def emit(*args,**kw):pass
            env=functions('app/domains/games/career/events.py',{'_reveal_loop'},{'get_room_state':lambda c:room,'asyncio':types.SimpleNamespace(sleep=sleep),'time':time,'_emit_reveal_state':emit})
            await env['_reveal_loop']('LOCAL',gs.state_version);self.assertEqual(gs.revealed_count,2)
        asyncio.run(exercise())

    def test_reconnect_payload_has_actual_answer_remaining(self):
        from app.domains.games.career.engine import CareerGameState
        async def exercise():
            gs=CareerGameState('a','b');gs.start_new_player({'id':1,'clubs':[{'name':'x'}]});gs.stage='buzzed';gs.buzzed_player='a';gs.answer_deadline=107;gs.reveal_started_at=98;gs.reveal_wait=5;out=[]
            class Sio:
                async def emit(self,event,payload,**kw):out.append(payload)
            env=functions('app/domains/games/career/events.py',{'send_career_reconnect_state'},{'get_room_state':lambda c:{'game_state':gs},'time':types.SimpleNamespace(time=lambda:100)})
            await env['send_career_reconnect_state'](Sio(),'LOCAL','a');self.assertEqual(out[0]['answerWindow'],7);self.assertEqual(out[0]['windowSeconds'],3);self.assertEqual(out[0]['stage'],'buzzed')
        asyncio.run(exercise())

if __name__=='__main__':unittest.main()
