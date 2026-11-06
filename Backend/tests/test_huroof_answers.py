import unittest
from app.core.huroof_answers import answer_letter, check_answer
class HuroofAnswerTests(unittest.TestCase):
 def accepted(self,typed,answer,letter,aliases=None):
  return check_answer(typed,answer,aliases,letter)['verdict']=='accept'
 def test_generic_prefixes_do_not_identify_a_country_or_city(self):
  for typed,answer,letter in [('جمهورية','جمهورية الكونغو الديمقراطية','ج'),('مدينة','مدينة بروكسل','م'),('غينيا','غينيا بيساو','غ'),('دومينيكا','دومينيكان','د')]:self.assertFalse(self.accepted(typed,answer,letter))
 def test_diacritics_article_and_hamza_variants(self):
  self.assertTrue(self.accepted('جَزائر','الجزائر','ج'))
  self.assertTrue(self.accepted('البانيا','ألبانيا','أ'))
  self.assertTrue(self.accepted('ال عمران','آل عمران','أ'))
  self.assertFalse(self.accepted('عمران','آل عمران','أ'))
 def test_alias_requires_reference_letter(self):
  self.assertTrue(self.accepted('ماغنسيوم','مغنيسيوم','م',['ماغنسيوم']))
  self.assertFalse(self.accepted('خارصين','زنك','ز',['خارصين']))
 def test_reference_initial_is_consistent(self):
  for text,letter in [('ٱلجزائر','ج'),('آل عمران','أ'),('ألبانيا','أ'),('الظاهرة','ظ')]:self.assertEqual(answer_letter(text),letter)
 def test_empty_and_non_list_metadata_fail_closed(self):
  self.assertFalse(self.accepted('','باريس','ب'))
  self.assertFalse(self.accepted('خاطئ','باريس','ب',{'خاطئ':True}))
