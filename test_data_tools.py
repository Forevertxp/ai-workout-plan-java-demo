import json
import tempfile
import unittest
from pathlib import Path
from audit_jsonl import audit
from build_dataset import build

BASE = Path(__file__).parent

class DataToolsTests(unittest.TestCase):
    def test_duplicate_questions_are_separate_from_record_duplicates(self):
        report = audit(BASE / 'data/synthetic_messages.jsonl')
        self.assertEqual((report['valid_records'], report['repeated_question_groups'],
                          report['question_occurrences_beyond_first'], report['exact_duplicate_records']), (3, 1, 2, 1))

    def test_malformed_json_is_reported_without_printing_private_content(self):
        with tempfile.TemporaryDirectory() as t:
            p = Path(t) / 'bad.jsonl'
            p.write_text('{"private": "secret-content"')
            report = audit(p)
            self.assertEqual(report['issues'], [{'line': 1, 'reason': 'invalid JSON'}])
            self.assertNotIn('secret-content', json.dumps(report))

    def test_member_groups_stay_together_and_feedback_is_not_model_input(self):
        with tempfile.TemporaryDirectory() as t:
            target = Path(t) / 'dataset'
            report = build(BASE / 'data/synthetic_reviews.jsonl', target)
            self.assertEqual(report['accepted'], 24)
            self.assertEqual(report['skipped'], 1)
            self.assertEqual(report['splits'], {'train': 20, 'validation': 2, 'test': 2})
            manifest = json.loads((target / 'manifest.json').read_text())
            groups = {}
            for row in manifest:
                groups.setdefault(row['memberGroup'], set()).add(row['split'])
            self.assertTrue(all(len(s) == 1 for s in groups.values()))
            for name in ('train', 'validation', 'test'):
                for line in (target / (name + '.jsonl')).read_text().splitlines():
                    prompt = json.loads(json.loads(line)['messages'][1]['content'])
                    self.assertEqual(set(prompt), {'assessment', 'candidates', 'requirements'})
            with self.assertRaises(ValueError):
                build(BASE / 'data/synthetic_reviews.jsonl', target)

    def test_reviewed_target_cannot_use_a_resource_absent_from_original_input(self):
        with tempfile.TemporaryDirectory() as t:
            rows = [json.loads(x) for x in (BASE / 'data/synthetic_reviews.jsonl').read_text().splitlines()]
            rows[0]['approvedPlan']['choices'][0]['projectId'] = 9999
            p = Path(t) / 'reviews.jsonl'
            p.write_text('\n'.join(json.dumps(r) for r in rows))
            with self.assertRaises(ValueError):
                build(p, Path(t) / 'out')

if __name__ == '__main__':
    unittest.main(verbosity=2)
