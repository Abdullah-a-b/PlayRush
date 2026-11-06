"""اختبارات خطة الغربلة: لا قاعدة بيانات أو ملفات إنتاج."""
import copy
import unittest
from scripts.apply_game_content_review import prepare_files

class ReviewTests(unittest.TestCase):
 def docs(self):return {'bank_questions.json':[{'id':'q1','q':'سؤال','a':'جواب'}],'bank_questions_auto.json':[],'whoami_characters.json':{'characters':[]},'knowledge_questions.json':{'questions':[]}}
 def change(self):
  old=self.docs()['bank_questions.json'][0];return {'game':'bank','id':'q1','before':old,'after':dict(old,q='صياغة دقيقة')}
 def test_preconditions_and_input_immutability(self):
  original=self.docs();before=copy.deepcopy(original);result=prepare_files({'changes':[self.change()]},original);self.assertEqual(original,before);self.assertEqual(result['bank_questions.json'][0]['q'],'صياغة دقيقة')
 def test_stale_snapshot_is_rejected(self):
  docs=self.docs();docs['bank_questions.json'][0]['q']='تحديث آخر'
  with self.assertRaises(RuntimeError):prepare_files({'changes':[self.change()]},docs)
 def test_identity_change_is_rejected(self):
  change=self.change();change['after']['id']='different'
  with self.assertRaises(ValueError):prepare_files({'changes':[change]},self.docs())
 def test_non_content_domain_is_rejected(self):
  change=self.change();change['game']='users'
  with self.assertRaises(ValueError):prepare_files({'changes':[change]},self.docs())
 def test_duplicate_edits_are_rejected(self):
  with self.assertRaises(ValueError):prepare_files({'changes':[self.change(),self.change()]},self.docs())
 def test_alias_collision_is_rejected(self):
  docs=self.docs();docs['knowledge_questions.json']['questions']=[{'id':'list','answers':['إجابة '+str(i) for i in range(15)]+['إجابة 0|اسم آخر']}]
  with self.assertRaises(ValueError):prepare_files({'changes':[]},docs)
 def test_manual_auto_duplicate_is_rejected(self):
  docs=self.docs();docs['bank_questions_auto.json']=[{'id':'auto','q':'سؤال','a':'جواب'}]
  with self.assertRaises(ValueError):prepare_files({'changes':[]},docs)
if __name__=='__main__':unittest.main()
