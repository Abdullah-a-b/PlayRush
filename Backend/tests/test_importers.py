"""اختبارات محتوى معزولة؛ لا تحميل .env أو اتصال بقاعدة الإنتاج."""
import ast, json, os, sys, tempfile, types, unittest
from pathlib import Path
from unittest.mock import patch, MagicMock
from sqlalchemy.orm import declarative_base
fake_database=types.ModuleType('app.infrastructure.database');fake_database.Base=declarative_base();fake_database.SessionLocal=MagicMock();fake_database.engine=MagicMock();sys.modules['app.infrastructure.database']=fake_database
from app.core import import_support as support, paths
from scripts import bank_questions_import as bank, huroof_questions_import as huroof, wikidata_import as career
from app.domains.games.importers import bank_importer, huroof_importer, career_importer, whoami_importer as who, knowledge_importer as knowledge
from app.domains.games.models import Question, CareerPlayer

def row(**kw):return {k:{'value':v} for k,v in kw.items()}
class Query:
 def __init__(self,s,target):self.s=s;self.target=target;self.rows=list(s.rows);self.start=0;self.end=None
 def filter(self,e):
  key=e.left.key;value=getattr(e.right,'value',None)
  self.rows=[r for r in self.rows if (getattr(r,key) is not None if e.operator.__name__=='is_not' else getattr(r,key)==value)];return self
 def order_by(self,f):self.rows.sort(key=lambda r:getattr(r,f.key));return self
 def offset(self,n):self.start=n;return self
 def limit(self,n):self.end=n;return self
 def all(self):
  rows=self.rows[self.start:][:self.end];return rows if isinstance(self.target,type) else [(getattr(r,self.target.key),) for r in rows]
 def first(self):return self.all()[0] if self.all() else None
 def count(self):return len(self.rows)
class Session:
 def __init__(self,rows=()):self.rows=list(rows);self.commits=0;self.rolled_back=False
 def query(self,t):return Query(self,t)
 def add(self,r):r.id=r.id or max([x.id or 0 for x in self.rows]+[0])+1;self.rows.append(r)
 def commit(self):self.commits+=1
 def rollback(self):self.rolled_back=True
 def close(self):pass
class ImportTests(unittest.TestCase):
 def setUp(self):
  self.tmp=tempfile.TemporaryDirectory();self.root=Path(self.tmp.name);self.ps=[patch.object(paths,'DATA_DIR',self.root),patch.object(support.time,'sleep',lambda _:None)]
  for p in self.ps:p.start()
 def tearDown(self):
  for p in reversed(self.ps):p.stop()
  self.tmp.cleanup()
 def countries(self):return [row(c='Q1',cLabelAr='دولة تجريبية',cap='Q2',capAr='عاصمة أولى',cur='Q3',curAr='عملة أولى',cont='Q4',contAr='قارة أولى')]
 def test_bank_ambiguity_order(self):
  rows=self.countries()+[row(c='Q1',cLabelAr='دولة تجريبية',cap='Q9',capAr='عاصمة ثانية',cur='Q8',curAr='عملة ثانية',cont='Q7',contAr='قارة ثانية')]
  self.assertEqual(bank.build_questions(rows),[]);self.assertEqual(bank.build_questions(rows),bank.build_questions(rows[::-1]))
 def test_bank_stable_id(self):
  rows=self.countries()+[row(c='Q20',cLabelAr='دولة أخرى',cap='Q21',capAr='مدينة أخرى')];self.assertEqual(bank.build_questions(rows),bank.build_questions(rows[::-1]));self.assertEqual(len({q['id'] for q in bank.build_questions(rows)}),4)
 def test_bank_keeps_seen_identity_updates_answer(self):
  rows=[row(c=f'Q{i+1}',cLabelAr=f'دولة {i}',cap=f'Q{i+101}',capAr=f'مدينة {i}') for i in range(31)];old=bank.build_questions(rows);old[0]['id']='legacy-id';old[0]['a']='قديم';support.atomic_json(self.root/'bank_questions_auto.json',old)
  with patch.object(bank,'fetch_rows',return_value=rows):result=bank.run_import()
  self.assertEqual(support.read_json(self.root/'bank_questions_auto.json')[0]['id'],'legacy-id');self.assertEqual(result['updated'],1);self.assertEqual(result['added'],0)
 def test_bank_small_response_preserves_file(self):
  p=self.root/'bank_questions_auto.json';support.atomic_json(p,[{'id':'keep'}])
  with patch.object(bank,'fetch_rows',return_value=[]):
   with self.assertRaises(RuntimeError):bank.run_import()
  self.assertEqual(support.read_json(p),[{'id':'keep'}])
 def test_atomic_backup(self):
  p=self.root/'x.json';support.atomic_json(p,{'x':1});support.atomic_json(p,{'x':2});self.assertEqual(support.read_json(p.with_suffix('.json.previous')),{'x':1})
 def test_bad_serialization_preserves_file(self):
  p=self.root/'x.json';support.atomic_json(p,{'x':1})
  with self.assertRaises(TypeError):support.atomic_json(p,{'x':object()})
  self.assertEqual(support.read_json(p),{'x':1})
 def test_corrupt_read_raises(self):
  p=self.root/'x.json';p.write_text('{')
  with self.assertRaises(ValueError):support.read_json(p,{})
 def test_lock(self):
  with support.import_lock(self.root/'lock') as a:
   with support.import_lock(self.root/'lock') as b:self.assertTrue(a);self.assertFalse(b)
 def test_zero_is_success(self):
  s=support.record_result({},dict(status='success',added=0),100);self.assertEqual(s['last_run'],100);self.assertFalse(support.due(s,700,101))
 def test_partial_has_retry(self):
  s=support.record_result({'last_run':50},{'status':'partial'},100);self.assertEqual(s['last_run'],50);self.assertFalse(support.due(s,10,200));self.assertTrue(support.due(s,10000,3700))
 def test_huroof_curated(self):
  qs=huroof.build_quran_questions()+huroof.build_curated_questions();self.assertEqual(len(qs),119);self.assertIn('ظ',{q['letter'] for q in qs})
 def test_huroof_rejects_ambiguous_capital(self):
  rows=self.countries()+[row(c='Q1',cLabelAr='دولة تجريبية',cap='Q9',capAr='عاصمة ثانية')];self.assertFalse(any(q['question_text'].startswith('عاصمة دولة') for q in huroof.build_country_questions(rows)))
 def test_huroof_source_identity(self):
  a=huroof.build_country_questions(self.countries());rows=self.countries();rows[0]['capAr']['value']='مدينة جديدة';b=huroof.build_country_questions(rows);self.assertEqual([q['source_id'] for q in a],[q['source_id'] for q in b])
 def test_huroof_ambiguous_author(self):self.assertEqual(huroof.build_extra_questions([row(item='Q1',itemAr='كتاب',answerAr='كاتب أول'),row(item='Q1',itemAr='كتاب',answerAr='كاتب ثان')],'book'),[])
 def test_huroof_upsert_and_manual_protection(self):
  auto=Question(id=1,game_mode='huroof',question_text='سؤال آلي',correct_answer='قديم',category='علوم',extra_data=json.dumps({'source':'auto_wikidata','source_id':'s1'}));manual=Question(id=2,game_mode='huroof',question_text='سؤال يدوي',correct_answer='محفوظ',category='علوم',extra_data='{}');session=Session([auto,manual]);q=dict(question_text='سؤال محدث',correct_answer='جديد',category='علوم',letter='ج',accepted_answers=['جديد'],source_id='s1')
  with patch.object(fake_database,'SessionLocal',return_value=session):result=huroof.save_to_db([q,{**q,'question_text':'سؤال يدوي','source_id':'s2'}])
  self.assertEqual(auto.id,1);self.assertEqual(auto.correct_answer,'جديد');self.assertEqual(manual.correct_answer,'محفوظ');self.assertEqual(result['manual_protected'],1);self.assertTrue(list((self.root/'backups').glob('huroof_*.json')))
 def test_huroof_idempotent(self):
  session=Session();q=dict(question_text='سؤال',correct_answer='جواب',category='عام',letter='ج',accepted_answers=['جواب'],source_id='s1')
  with patch.object(fake_database,'SessionLocal',return_value=session):self.assertEqual(huroof.save_to_db([q])['added'],1);self.assertEqual(huroof.save_to_db([q])['unchanged'],1)
 def test_huroof_bad_metadata_protected(self):
  q=Question(id=1,game_mode='huroof',question_text='سؤال',correct_answer='قديم',extra_data='{')
  with patch.object(fake_database,'SessionLocal',return_value=Session([q])):r=huroof.save_to_db([dict(question_text='سؤال',correct_answer='جديد',category='عام',letter='ج',accepted_answers=[])])
  self.assertEqual(r['manual_protected'],1)
 def test_career_deceased_open_contract(self):
  e={'claims':{'P570':[{'mainsnak':{'datavalue':{'value':{'time':'+2020-01-01'}}}}]}};self.assertEqual(career.detect_status(e,[{'has_end':False,'end':None}]),'retired')
 def test_career_deprecated_death(self):
  e={'claims':{'P570':[{'rank':'deprecated','mainsnak':{'datavalue':{'value':'x'}}}]}};self.assertEqual(career.detect_status(e,[{'has_end':False,'end':None}]),'current')
 def test_career_first_name(self):self.assertNotIn('محمد',career.gen_accepted('محمد صلاح','Mohamed Salah'))
 def test_career_stable_query(self):
  r=MagicMock();r.json.return_value={'results':{'bindings':[]}}
  with patch.object(career,'_get_with_retry',return_value=r) as get:career.sparql_top_players(10,45)
  self.assertIn('ORDER BY DESC(?sitelinks) ?player',get.call_args.kwargs['params']['query'])
 def test_career_wiki_failure_unknown(self):
  with patch.object(career,'_get_with_retry',side_effect=RuntimeError('offline')):out=career._ar_article_lengths(['عنوان'])
  self.assertIsNone(out['عنوان'])
 def test_whoami_unknown_death(self):self.assertNotIn('قيد الحياة',who.build_hints('اسم','دولة','مهنة',1800,None)[0])
 def test_whoami_multiple_nationalities(self):
  rows=[row(p='http://www.wikidata.org/entity/Q1',pAr='اسم تجريبي',natAr='دولة أولى',occAr='عالم',birth='+1800-01-01T00:00:00Z'),row(p='http://www.wikidata.org/entity/Q1',pAr='اسم تجريبي',natAr='دولة ثانية',occAr='عالم',birth='+1800-01-01T00:00:00Z')];a=who._character_rows(rows,'Q901','علماء');self.assertEqual(a,who._character_rows(rows[::-1],'Q901','علماء'));self.assertEqual(len(a),1);self.assertIn('دولة ثانية',a[0]['hints'][1])
 def test_whoami_pagination(self):self.assertIn('ORDER BY DESC(?links) ?p LIMIT 60 OFFSET 60',who._query_for('Q901',60))
 def test_whoami_first_name(self):self.assertNotIn('محمد',who._gen_accepted('محمد صلاح','Mohamed Salah'))
 def test_knowledge_normalized_dedup(self):self.assertEqual(len(knowledge._merge_answers(['ألمانيا|المانيا'],['المانيا'])),1)
 def test_knowledge_pagination(self):
  rows=[row(cAr='مدينة '+str(i)) for i in range(200)]
  with patch.object(knowledge,'sparql_rows',side_effect=[rows,[]]) as fetch:knowledge._run_query('SELECT DISTINCT ?cAr WHERE { ?c rdfs:label ?cAr } LIMIT 120')
  self.assertEqual(fetch.call_count,2);self.assertIn('OFFSET 200',fetch.call_args.args[0]);self.assertNotIn('LIMIT 120',fetch.call_args.args[0])
 def test_knowledge_existing_template_refreshes(self):
  data=self.root/'knowledge.json';state=self.root/'state.json';words=['إجابة '+str(i) for i in range(20)];support.atomic_json(data,{'questions':[dict(id='new',q='قائمة',answers=words[:16],source='wikidata',manual_answers=[])]})
  with patch.object(knowledge,'_DATA_FILE',str(data)),patch.object(knowledge,'STATE_FILE',str(state)),patch.object(knowledge,'QUERIES',{}),patch.object(knowledge,'NEW_QUESTION_TEMPLATES',{'new':dict(q='قائمة',cat='عام',sparql='query')}),patch.object(knowledge,'_run_query',return_value=words),patch.dict(sys.modules,{'app.domains.games.knowledge.events':types.SimpleNamespace(_QCACHE={'loaded':True})}):r=knowledge._run_once()
  self.assertEqual(r['updated'],1);self.assertEqual(len(support.read_json(data)['questions'][0]['answers']),20)
 def test_reader_syntax(self):
  root=Path(__file__).resolve().parents[1]
  for name in ('bank','huroof','whoami','knowledge'):ast.parse((root/f'app/domains/games/{name}/events.py').read_text(encoding='utf-8'))

 def _player(self):
  return CareerPlayer(id=1,wikidata_id='Q100',name='لاعب تجريبي',status='current',clubs=json.dumps([{'name':'نادي تجريبي','logo':'old.png'}]),accepted_answers='[]',difficulty='easy',active=False,era='2010-الآن')
 def _entities(self):
  return {'Q100':{'labels':{'ar':{'value':'لاعب تجريبي'}},'sitelinks':{'arwiki':{'title':'مقال اللاعب'}},'claims':{'P54':[{'mainsnak':{'datavalue':{'value':{'id':'Q200'}}},'qualifiers':{'P580':[{'datavalue':{'value':{'time':'+2010-01-01T00:00:00Z'}}}]}}],'P570':[{'mainsnak':{'datavalue':{'value':{'time':'+2020-01-01T00:00:00Z'}}}}]}},'Q200':{'labels':{'ar':{'value':'نادي تجريبي'},'en':{'value':'Example FC'}},'claims':{}}}
 def test_career_real_refresh_updates_preserves_curated_state(self):
  player=self._player();session=Session([player]);entities=self._entities();career._ENTITY_CACHE['stale']={}
  with patch.object(career,'SessionLocal',return_value=session),patch.object(career,'_ensure_wikidata_column'),patch.object(career,'wd_get_entities',side_effect=lambda ids:{q:entities[q] for q in ids}),patch.object(career,'_ar_article_lengths',return_value={'مقال اللاعب':None}):result=career.run_import(refresh=True,player_qids=['Q100'],skip_logos=True,log=lambda _:None)
  self.assertEqual(result['updated'],1);self.assertEqual(player.id,1);self.assertEqual(player.status,'retired');self.assertEqual(player.difficulty,'easy');self.assertFalse(player.active);self.assertEqual(json.loads(player.clubs)[0]['logo'],'old.png');self.assertNotIn('الآن',player.era);self.assertNotIn('stale',career._ENTITY_CACHE)
 def test_career_incomplete_clubs_not_committed(self):
  player=self._player();session=Session([player]);entities=self._entities()
  with patch.object(career,'SessionLocal',return_value=session),patch.object(career,'_ensure_wikidata_column'),patch.object(career,'wd_get_entities',side_effect=lambda ids:{q:entities[q] for q in ids if q=='Q100'}),patch.object(career,'_ar_article_lengths',return_value={}):
   with self.assertRaises(RuntimeError):career.run_import(refresh=True,player_qids=['Q100'],skip_logos=True,log=lambda _:None)
  self.assertEqual(session.commits,0);self.assertEqual(player.status,'current')
 def test_bank_loop_zero_records_success(self):
  state=self.root/'state.json'
  with patch.object(bank_importer,'STATE_FILE',str(state)),patch.object(bank,'run_import',return_value={'status':'success','added':0,'updated':0}):bank_importer._run_once()
  self.assertGreater(support.read_json(state)['last_run'],0)
 def test_import_failure_retries_without_success_timestamp(self):
  state=self.root/'state.json';support.atomic_json(state,{'last_run':1})
  with patch.object(huroof_importer,'STATE_FILE',str(state)),patch.object(huroof,'run_import',side_effect=RuntimeError('offline')):result=huroof_importer._run_once()
  saved=support.read_json(state);self.assertEqual(saved['last_run'],1);self.assertIn('retry_after',saved);self.assertEqual(result['status'],'error')
 def test_whoami_source_failure_preserves_data(self):
  data=self.root/'who.json';state=self.root/'state.json';doc={'characters':[{'id':'manual','name':'شخص يدوي'}]};support.atomic_json(data,doc)
  with patch.object(who,'_DATA_FILE',str(data)),patch.object(who,'STATE_FILE',str(state)),patch.object(who,'OCCUPATIONS',{'Q901':'علماء'}),patch.object(who,'_run_query',side_effect=RuntimeError('offline')):result=who._run_once()
  self.assertEqual(support.read_json(data),doc);self.assertEqual(result['status'],'partial');self.assertIn('retry_after',support.read_json(state)['sources']['Q901:discover'])
 def test_whoami_updates_legacy_auto_keeps_identity(self):
  data=self.root/'who.json';state=self.root/'state.json';support.atomic_json(data,{'characters':[{'id':'wd_Q901_3','name':'شخص تجريبي','hints':['قديم']}]})
  rows=[row(p='http://www.wikidata.org/entity/Q1',pAr='شخص تجريبي',natAr='دولة',occAr='عالم',birth='+1800-01-01T00:00:00Z',death='+1870-01-01T00:00:00Z')]
  with patch.object(who,'_DATA_FILE',str(data)),patch.object(who,'STATE_FILE',str(state)),patch.object(who,'OCCUPATIONS',{'Q901':'علماء'}),patch.object(who,'_run_query',return_value=rows),patch.dict(sys.modules,{'app.domains.games.whoami.events':types.SimpleNamespace(_chars_cache=[])}):result=who._run_once()
  saved=support.read_json(data)['characters'];self.assertEqual(len(saved),1);self.assertEqual(saved[0]['id'],'wd_Q901_3');self.assertEqual(saved[0]['wikidata_id'],'Q1');self.assertEqual(result['updated'],1)
 def test_knowledge_partial_failure_only_retries_failed_source(self):
  data=self.root/'knowledge.json';state=self.root/'state.json';support.atomic_json(data,{'questions':[]});words=['إجابة '+str(i) for i in range(20)];templates={k:dict(q=k,cat='عام',sparql=k) for k in ['good','bad']}
  def get(q):
   if q=='bad':raise RuntimeError('offline')
   return words
  with patch.object(knowledge,'_DATA_FILE',str(data)),patch.object(knowledge,'STATE_FILE',str(state)),patch.object(knowledge,'QUERIES',{}),patch.object(knowledge,'NEW_QUESTION_TEMPLATES',templates),patch.object(knowledge,'_run_query',side_effect=get),patch.dict(sys.modules,{'app.domains.games.knowledge.events':types.SimpleNamespace(_QCACHE={'loaded':True})}):result=knowledge._run_once()
  sources=support.read_json(state)['sources'];self.assertIn('last_run',sources['good']);self.assertNotIn('last_run',sources['bad']);self.assertEqual(result['failed_sources'],['bad'])
 def _reader(self,game,name,env):
  root=Path(__file__).resolve().parents[1];tree=ast.parse((root/f'app/domains/games/{game}/events.py').read_text(encoding='utf-8'));nodes=[n for n in tree.body if isinstance(n,ast.FunctionDef) and n.name==name];exec(compile(ast.Module(body=nodes,type_ignores=[]),'reader','exec'),env);return env[name]
 def test_bank_reader_reload_and_text_dedup(self):
  support.atomic_json(self.root/'bank_questions.json',[dict(id='m1',q='سؤال يدوي',a='جواب')]);support.atomic_json(self.root/'bank_questions_auto.json',[dict(id='a1',q='سؤال يدوي',a='غيره')]);env=dict(json=json,os=os,_QUESTIONS=None,_QUESTIONS_STAMP=None);read=self._reader('bank','_load_questions',env)
  self.assertEqual(len(read()),1);support.atomic_json(self.root/'bank_questions_auto.json',[dict(id='a2',q='سؤال جديد',a='جواب')]);env['_QUESTIONS_STAMP']=None;self.assertEqual(len(read()),2)
 def test_whoami_reader_reload(self):
  p=self.root/'who.json';support.atomic_json(p,{'characters':[{'id':'a'}]});env=dict(json=json,_CHARS_FILE=str(p),_chars_cache=None,_chars_stamp=None);read=self._reader('whoami','_load_pool',env);self.assertEqual(read()[0]['id'],'a');support.atomic_json(p,{'characters':[{'id':'b'}]});env['_chars_stamp']=None;self.assertEqual(read()[0]['id'],'b')


 def test_huroof_stale_source_is_quarantined_not_deleted(self):
  old=Question(id=1,game_mode='huroof',question_text='عاصمة قديمة',correct_answer='قديم',extra_data=json.dumps({'source':'auto_wikidata','source_id':'wd_cap_old','active':True}))
  session=Session([old])
  with patch.object(fake_database,'SessionLocal',return_value=session):r=huroof.save_to_db([],complete_groups=['countries'])
  self.assertEqual(r['deactivated'],1);self.assertFalse(json.loads(old.extra_data)['active']);self.assertEqual(len(session.rows),1)
 def test_huroof_failed_source_not_quarantined(self):
  old=Question(id=1,game_mode='huroof',question_text='عاصمة',correct_answer='جواب',extra_data=json.dumps({'source':'auto_wikidata','source_id':'wd_cap_old','active':True}))
  with patch.object(fake_database,'SessionLocal',return_value=Session([old])):r=huroof.save_to_db([],complete_groups=['elements'])
  self.assertEqual(r['deactivated'],0);self.assertTrue(json.loads(old.extra_data)['active'])
 def test_language_iso_code_is_valid_prompt(self):
  self.assertEqual(len(huroof.build_extra_questions([row(item='Q1',itemAr='ar',answerAr='العربية')],'language')),1)
 def test_conflicting_same_text_is_not_served(self):
  self.assertEqual(support.unambiguous_questions([dict(q='سؤال',a='أول',id='a'),dict(q='سؤال',a='ثان',id='b')]),[])


 def test_persistent_seed_never_overwrites_or_resets_state(self):
  import subprocess
  env=dict(os.environ,PLAYRUSH_DATA_DIR=str(self.root/'durable'))
  code="from app.core.paths import DATA_DIR;print(DATA_DIR)"
  subprocess.run([sys.executable,'-c',code],env=env,check=True,capture_output=True)
  p=self.root/'durable'/'bank_questions_auto.json';support.atomic_json(p,[{'id':'live-newer-content'}])
  subprocess.run([sys.executable,'-c',code],env=env,check=True,capture_output=True)
  self.assertEqual(support.read_json(p),[{'id':'live-newer-content'}]);self.assertFalse((self.root/'durable'/'career_import_state.json').exists())
 def test_reviewed_variants_do_not_invent_words(self):
  from scripts.answer_variants import spelling_variants
  self.assertNotIn('الغنيه',spelling_variants('الجنيه'));self.assertIn('سنتياجو',spelling_variants('سانتياغو'))
 def test_legacy_ambiguous_auto_question_quarantined(self):
  old=Question(id=1,game_mode='huroof',question_text='عاصمة دولة متعددة العواصم',correct_answer='جواب اعتباطي',extra_data=json.dumps({'source':'auto_wikidata'}))
  with patch.object(fake_database,'SessionLocal',return_value=Session([old])):r=huroof.save_to_db([],complete_groups=['countries'])
  self.assertEqual(r['deactivated'],1);self.assertFalse(json.loads(old.extra_data)['active'])


 def test_knowledge_reader_works_with_durable_path(self):
  p=self.root/'knowledge.json';support.atomic_json(p,{'questions':[dict(id='manual',q='قائمة',answers=['جواب '+str(i) for i in range(15)])]})
  env=dict(json=json,os=os,_DATA_FILE=str(p),_QCACHE={'loaded':False,'questions':[]},_norm=lambda x:x)
  read=self._reader('knowledge','_load_questions',env);pool=read();self.assertEqual({q['id'] for q in pool},{'manual','kq_surahs'})


 def test_early_retry_check_keeps_pending_failure(self):
  data=self.root/'who.json';state=self.root/'state.json';future=__import__('time').time()+1000
  support.atomic_json(data,{'characters':[]});support.atomic_json(state,{'sources':{'Q901:discover':{'retry_after':future},'Q901:refresh':{'last_run':__import__('time').time()}}})
  with patch.object(who,'_DATA_FILE',str(data)),patch.object(who,'STATE_FILE',str(state)),patch.object(who,'OCCUPATIONS',{'Q901':'علماء'}),patch.object(who,'_run_query') as get:r=who._run_once()
  self.assertEqual(r['status'],'partial');self.assertEqual(support.read_json(state)['retry_after'],future);get.assert_not_called()
 def test_huroof_list_metadata_is_protected(self):
  q=Question(id=1,game_mode='huroof',question_text='سؤال',correct_answer='قديم',extra_data='[]')
  with patch.object(fake_database,'SessionLocal',return_value=Session([q])):r=huroof.save_to_db([dict(question_text='سؤال',correct_answer='جديد',category='عام',letter='ج',accepted_answers=[])])
  self.assertEqual(r['manual_protected'],1)


 def test_career_background_import_never_runs_schema_ddl(self):
  session=Session()
  with patch.object(career,'SessionLocal',return_value=session),patch.object(career,'_ensure_wikidata_column') as ddl:career.run_import(player_qids=[],refresh=True,log=lambda _:None)
  ddl.assert_not_called();self.assertTrue(session.rolled_back)


 def test_knowledge_alias_overlap_is_one_answer(self):
  merged=knowledge._merge_answers(['اسم شائع|اسم رسمي'],['اسم رسمي'])
  self.assertEqual(len(merged),1);self.assertIn('اسم شائع',merged[0]);self.assertIn('اسم رسمي',merged[0])

if __name__=='__main__':unittest.main()
