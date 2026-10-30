"""Audit message-format JSONL without emitting its private text. Python 3.10+."""
import argparse
import collections
import hashlib
import json
from pathlib import Path


def audit(path):
    prompts = collections.Counter()
    records = collections.Counter()
    issues = []
    total = valid = templates = json_answers = 0
    expected = ['system', 'user', 'assistant']
    for number, line in enumerate(Path(path).read_text(encoding='utf-8').splitlines(), 1):
        if not line.strip():
            continue
        total += 1
        try:
            record = json.loads(line)
            messages = record.get('messages') if isinstance(record, dict) else None
            if not isinstance(messages, list) or len(messages) != 3:
                raise ValueError('expected exactly three messages')
            if not all(isinstance(m, dict) for m in messages):
                raise ValueError('each message must be an object')
            if [m.get('role') for m in messages] != expected:
                raise ValueError('role sequence must be system,user,assistant')
            if not all(isinstance(m.get('content'), str) and m['content'].strip() for m in messages):
                raise ValueError('content must be non-empty strings')
            valid += 1
            prompts[messages[1]['content']] += 1
            records[json.dumps(record, sort_keys=True, ensure_ascii=False)] += 1
            templates += messages[1]['content'].startswith('请介绍')
            try:
                json.loads(messages[2]['content'])
                json_answers += 1
            except json.JSONDecodeError:
                pass
        except (json.JSONDecodeError, ValueError) as e:
            # Do not print raw source text or decoder excerpts.
            issues.append({'line': number, 'reason': 'invalid JSON' if isinstance(e, json.JSONDecodeError) else str(e)})
    return dict(records=total, valid_records=valid, distinct_questions=len(prompts),
                repeated_question_groups=sum(n > 1 for n in prompts.values()),
                question_occurrences_beyond_first=sum(n - 1 for n in prompts.values()),
                exact_duplicate_records=sum(n - 1 for n in records.values()),
                introduction_template_questions=templates, parseable_json_answers=json_answers,
                sha256=hashlib.sha256(Path(path).read_bytes()).hexdigest(), issues=issues)


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('file')
    print(json.dumps(audit(parser.parse_args().file), indent=2))
