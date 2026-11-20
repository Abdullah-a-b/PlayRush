"""اختبارات المصدر المحدود بلا شبكة أو قاعدة بيانات أو إعدادات سرية."""
import unittest
from unittest.mock import Mock, patch

from scripts import huroof_diverse_facts as source


def statement(target, **extra):
    return {"rank": "normal", "mainsnak": {"snaktype": "value",
            "datavalue": {"value": {"id": target}}}, **extra}


def entities():
    return {item: {"id": item, "lastrevid": 123, "claims": {prop: [statement(target)]}}
            for item, prop, target, *_ in source.FACTS}


class DiverseFactsTests(unittest.TestCase):
    def test_reviewed_collection_has_four_categories_and_explicit_difficulties(self):
        questions = source.build_questions(entities())
        self.assertEqual(len(questions), 20)
        self.assertEqual(len({q['source_id'] for q in questions}), 20)
        self.assertEqual({q['category'] for q in questions}, {'رياضة', 'أدب', 'فنون', 'فضاء'})
        self.assertEqual({q['difficulty'] for q in questions}, {'easy', 'medium'})
        self.assertTrue(all(q['letter'] and q['correct_answer'] in q['accepted_answers'] for q in questions))

    def test_conflicting_normal_or_preferred_target_is_rejected(self):
        for rank in ('normal', 'preferred'):
            data = entities()
            item, prop, *_ = source.FACTS[0]
            data[item]['claims'][prop].append(statement('Q999', rank=rank))
            self.assertEqual(len(source.build_questions(data)), 19)

    def test_unknown_qualified_or_malformed_value_is_rejected(self):
        for claim in ({'mainsnak': {'snaktype': 'somevalue'}},
                      statement('Q847', qualifiers={'P580': []}),
                      {'mainsnak': {'snaktype': 'value', 'datavalue': 'bad'}}, None):
            data = entities()
            item, prop, *_ = source.FACTS[0]
            data[item]['claims'][prop].append(claim)
            self.assertEqual(len(source.build_questions(data)), 19)

    def test_deprecated_claim_and_duplicate_target_do_not_create_conflict(self):
        data = entities()
        item, prop, target, *_ = source.FACTS[0]
        data[item]['claims'][prop] += [statement('Q999', rank='deprecated'), statement(target)]
        self.assertEqual(len(source.build_questions(data)), 20)

    def test_changed_relation_requires_review_instead_of_new_unreviewed_answer(self):
        data = entities()
        item, prop, *_ = source.FACTS[0]
        data[item]['claims'][prop] = [statement('Q999')]
        self.assertEqual(len(source.build_questions(data)), 19)

    def test_labels_cannot_rewrite_reviewed_text_aliases_or_identity(self):
        data = entities()
        original = source.build_questions(data)
        for item in data.values():
            item['labels'] = {'ar': {'value': 'نص غير مراجع'}}
            item['aliases'] = {'ar': [{'value': 'بديل غير مراجع'}]}
        self.assertEqual(source.build_questions(data), original)
        self.assertIn('دافنشي', next(q for q in original if 'الموناليزا' in q['question_text'])['accepted_answers'])

    def test_missing_entity_or_wrong_id_does_not_generate_question(self):
        data = entities()
        item = source.FACTS[0][0]
        for entity in ({'missing': ''}, {'id': 'Q999'}, None):
            data[item] = entity
            self.assertEqual(len(source.build_questions(data)), 19)

    def test_fetch_uses_one_bounded_request_and_returns_complete_entities(self):
        response = Mock()
        response.json.return_value = {'entities': entities()}
        with patch('requests.get', return_value=response) as get:
            self.assertEqual(source.fetch_entities(), entities())
        get.assert_called_once()
        self.assertEqual(get.call_args.kwargs['timeout'], (5, 20))
        self.assertEqual(len(get.call_args.kwargs['params']['ids'].split('|')), 20)

    def test_incomplete_response_is_error_not_successful_empty_source(self):
        for payload in ({'error': {'code': 'maxlag'}}, {'entities': {}}, [],
                        {'entities': {q: None for q in entities()}}):
            response = Mock()
            response.json.return_value = payload
            with patch('requests.get', return_value=response), self.assertRaises(ValueError):
                source.fetch_entities()

    def test_transport_failure_is_propagated_for_retry(self):
        import requests
        with patch('requests.get', side_effect=requests.Timeout), self.assertRaises(requests.Timeout):
            source.fetch_entities()

    def test_partial_relationship_snapshot_is_not_reported_as_complete(self):
        data = entities()
        data[source.FACTS[0][0]]['claims'] = {}
        with patch.object(source, 'fetch_entities', return_value=data), self.assertRaises(ValueError):
            source.fetch_questions()
        with patch.object(source, 'fetch_entities', return_value=entities()):
            self.assertEqual(len(source.fetch_questions()), 20)


if __name__ == '__main__':
    unittest.main()
