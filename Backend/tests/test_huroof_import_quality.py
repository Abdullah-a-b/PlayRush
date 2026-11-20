"""اختبارات جودة الاستيراد مع قاعدة وهمية؛ لا أسرار أو اتصالات خارجية."""
import json
import tempfile
import time
import unittest
from pathlib import Path
from unittest.mock import patch

if __package__:
    from tests.test_importers import Question, Session, fake_database, huroof, paths, support, row
else:
    from test_importers import Question, Session, fake_database, huroof, paths, support, row


class HuroofImportQualityTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)
        self.patches = [
            patch.object(paths, 'DATA_DIR', self.root),
            patch.dict(huroof.os.environ, {'HUROOF_BOOK_IMPORT': '0', 'HUROOF_DIVERSE_IMPORT': '0'}),
        ]
        for item in self.patches:
            item.start()

    def tearDown(self):
        for item in reversed(self.patches):
            item.stop()
        self.tmp.cleanup()

    def question(self, **changes):
        return {
            'question_text': 'حيوان أليف يموء', 'correct_answer': 'قط',
            'category': 'حيوانات', 'letter': 'ق',
            'accepted_answers': ['قط'], 'source_id': 'wd_test_cat',
            **changes,
        }

    def existing(self, **metadata):
        return Question(
            id=1, game_mode='huroof', question_text='حيوان أليف يموء',
            correct_answer='قط', category='حيوانات',
            extra_data=json.dumps({
                'source': 'auto_wikidata', 'source_id': 'wd_test_cat',
                'active': True, 'letter': 'ق', 'accepted_answers': ['قط'],
                **metadata,
            }, ensure_ascii=False),
        )

    def test_refresh_preserves_reviewed_metadata_and_unchanged_answer_aliases(self):
        old = self.existing(
            difficulty='easy', accepted_answers=['قط', 'هر'],
            _curation={'reviewed_at': '2026-11-15', 'reviewer': 'content-review'},
        )
        session = Session([old])
        with patch.object(fake_database, 'SessionLocal', return_value=session):
            huroof.save_to_db([self.question()])
            huroof.save_to_db([self.question()])
        saved = json.loads(old.extra_data)
        self.assertEqual(saved.get('difficulty'), 'easy')
        self.assertEqual(saved.get('_curation'), {
            'reviewed_at': '2026-11-15', 'reviewer': 'content-review',
        })
        self.assertIn('هر', saved['accepted_answers'])
        self.assertEqual(len(session.rows), 1)

    def test_refresh_does_not_transfer_aliases_to_a_changed_answer(self):
        old = self.existing(accepted_answers=['قط', 'هر'])
        with patch.object(fake_database, 'SessionLocal', return_value=Session([old])):
            huroof.save_to_db([self.question(
                question_text='حيوان أليف ينبح', correct_answer='كلب',
                letter='ك', accepted_answers=['كلب'],
            )])
        saved = json.loads(old.extra_data)
        self.assertNotIn('قط', saved['accepted_answers'])
        self.assertNotIn('هر', saved['accepted_answers'])
        self.assertEqual(old.correct_answer, 'كلب')

    def test_invalid_answer_is_not_inserted_into_active_question_bank(self):
        session = Session()
        with patch.object(fake_database, 'SessionLocal', return_value=session):
            huroof.save_to_db([self.question(correct_answer='???', accepted_answers=['???'])])
        self.assertEqual(session.rows, [])

    def test_malformed_remote_rows_cannot_retire_an_existing_family(self):
        old = self.existing(source_id='wd_cap_existing')
        session = Session([old])
        with patch.object(fake_database, 'SessionLocal', return_value=session), \
                patch.object(huroof, 'fetch_rows', return_value=[{} for _ in range(60)]):
            result = huroof.run_import()
        self.assertNotEqual(result['status'], 'success')
        self.assertTrue(json.loads(old.extra_data)['active'])

    def test_duplicate_bindings_are_not_proof_of_complete_source_coverage(self):
        old = self.existing(source_id='wd_cap_existing')
        single = row(
            c='http://www.wikidata.org/entity/Q79', cLabelAr='مصر',
            cLabelEn='Egypt', cap='http://www.wikidata.org/entity/Q85',
            capAr='القاهرة', capEn='Cairo',
        )
        with patch.object(fake_database, 'SessionLocal', return_value=Session([old])), \
                patch.object(huroof, 'fetch_rows', return_value=[single] * 60):
            result = huroof.run_import()
        self.assertNotEqual(result['status'], 'success')
        self.assertTrue(json.loads(old.extra_data)['active'])

    def test_failed_remote_fetch_does_not_reapply_old_cached_fact(self):
        cached = row(
            c='http://www.wikidata.org/entity/Q_TEST', cLabelAr='بلاد تجريبية',
            cLabelEn='Test', cap='http://www.wikidata.org/entity/Q_OLD',
            capAr='مدينة قديمة', capEn='Old city',
        )
        sid = support.stable_id('cap', 'http://www.wikidata.org/entity/Q_TEST')
        old = self.existing(source_id=sid)
        old.question_text = 'عاصمة دولة بلاد تجريبية'
        old.correct_answer = 'مدينة جديدة'
        support.atomic_json(self.root / 'huroof_source_snapshots.json', {
            'countries': {'rows': [cached], 'last_success': time.time() - 14 * 86400},
        })
        with patch.object(fake_database, 'SessionLocal', return_value=Session([old])), \
                patch.object(huroof, 'fetch_rows', side_effect=RuntimeError('offline')):
            result = huroof.run_import()
        self.assertNotEqual(result['status'], 'success')
        self.assertEqual(old.correct_answer, 'مدينة جديدة')
        self.assertTrue(json.loads(old.extra_data)['active'])

    def test_explicit_inactive_review_retires_existing_row_in_partial_import(self):
        old = self.existing()
        original_loads = json.loads

        def reviewed_loads(text, *args, **kwargs):
            document = original_loads(text, *args, **kwargs)
            if isinstance(document, dict) and 'rules' in document:
                document['rules']['wd_test_cat'] = {'active': False}
            return document

        with patch.object(fake_database, 'SessionLocal', return_value=Session([old])), \
                patch.object(huroof.json, 'loads', side_effect=reviewed_loads):
            huroof.save_to_db([self.question()])
        self.assertFalse(json.loads(old.extra_data)['active'])

    def test_conflicting_duplicate_questions_are_rejected_in_any_order(self):
        first = self.question(question_text='ما عاصمة البلاد؟', correct_answer='شرق', accepted_answers=['شرق'])
        second = self.question(question_text='ما عاصمة البلاد؟', correct_answer='غرب', accepted_answers=['غرب'], source_id='wd_test_other')
        for batch in ([first, second], [second, first]):
            with self.subTest(first_answer=batch[0]['correct_answer']):
                session = Session()
                with patch.object(fake_database, 'SessionLocal', return_value=session):
                    huroof.save_to_db(batch)
                self.assertEqual(session.rows, [])

    def test_text_match_cannot_steal_a_different_source_identity(self):
        old = self.existing(source_id='wd_z')
        session = Session([old])
        incoming = [self.question(source_id='wd_a'),
                    self.question(source_id='wd_z', question_text='حيوان صغير يموء')]
        with patch.object(fake_database, 'SessionLocal', return_value=session):
            result = huroof.save_to_db(incoming)
        self.assertEqual(result['identity_conflicts'], 1)
        self.assertEqual(json.loads(old.extra_data)['source_id'], 'wd_z')
        self.assertEqual(old.question_text, 'حيوان صغير يموء')
        self.assertEqual(len(session.rows), 1)

    def test_dry_run_never_saves_database_or_cache(self):
        with patch.object(huroof, 'fetch_rows', side_effect=RuntimeError('offline')), \
                patch.object(huroof, 'save_to_db') as save:
            result = huroof.run_import(dry_run=True)
        save.assert_not_called()
        self.assertTrue(result['dry_run'])
        self.assertFalse((self.root / 'huroof_source_snapshots.json').exists())

    def test_familiar_source_is_saved_once_then_read_from_cache(self):
        from scripts import huroof_diverse_facts as diverse
        session = Session()
        with patch.dict(huroof.os.environ, {'HUROOF_DIVERSE_IMPORT': '1'}), \
                patch.object(diverse, 'fetch_questions', return_value=[self.question(difficulty='easy')]) as fetch, \
                patch.object(huroof, 'fetch_rows', side_effect=RuntimeError('offline')), \
                patch.object(fake_database, 'SessionLocal', return_value=session):
            first = huroof.run_import()
            second = huroof.run_import()
        fetch.assert_called_once()
        self.assertEqual(first['sources']['familiar']['valid_questions'], 1)
        self.assertEqual(second['sources']['familiar']['status'], 'cached')
        self.assertEqual(second['added'], 0)


if __name__ == '__main__':
    unittest.main()
