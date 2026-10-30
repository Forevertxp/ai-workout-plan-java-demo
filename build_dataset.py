"""Proposed review-to-SFT workflow using synthetic fixtures, not the production app."""
import argparse
import hashlib
import json
from pathlib import Path

SYSTEM = ('Create a draft using only the supplied candidate resources. '
          'Return a JSON object with a non-empty choices array. '
          'Each choice must contain categoryId, projectId, amount and unit.')


def build(source, destination):
    rows = [json.loads(x) for x in Path(source).read_text().splitlines() if x.strip()]
    accepted, skipped = [], []
    for row in rows:
        if row.get('reviewStatus') != 'approved' or row.get('score', 0) < 4:
            skipped.append(row['sampleId'])
            continue
        context, target = row['generationInput'], row['approvedPlan']
        allowed = {(c['categoryId'], c['projectId']): c for c in context['candidates']}
        choices = target.get('choices', [])
        if not choices:
            raise ValueError('approved target is empty: ' + row['sampleId'])
        for choice in choices:
            c = allowed.get((choice['categoryId'], choice['projectId']))
            if not c or choice['unit'] not in c['allowedUnits']:
                raise ValueError('approved target violates its original candidate snapshot: ' + row['sampleId'])
        accepted.append(row)
    # Rank entire member groups deterministically; split before exporting samples.
    groups = sorted({r['memberGroup'] for r in accepted},
                    key=lambda g: hashlib.sha256(('demo-v1:' + g).encode()).hexdigest())
    if len(groups) < 3:
        raise ValueError('at least three member groups are needed for this demo split')
    held_out = max(1, len(groups) // 10)
    split = {g: ('test' if i < held_out else 'validation' if i < 2 * held_out else 'train')
             for i, g in enumerate(groups)}
    result = {name: [] for name in ('train', 'validation', 'test')}
    manifest = []
    for row in accepted:
        name = split[row['memberGroup']]
        # Explicit projection: scores, later outcomes and reviewer identity never become model input.
        sample = {'messages': [
            {'role': 'system', 'content': SYSTEM},
            {'role': 'user', 'content': json.dumps(row['generationInput'], ensure_ascii=False, sort_keys=True)},
            {'role': 'assistant', 'content': json.dumps(row['approvedPlan'], ensure_ascii=False, sort_keys=True)}]}
        result[name].append(sample)
        digest = hashlib.sha256(json.dumps(sample, sort_keys=True).encode()).hexdigest()
        manifest.append({key: row[key] for key in ('sampleId', 'memberGroup', 'generationId', 'modelVersion')}
                        | {'split': name, 'sampleSha256': digest, 'datasetVersion': 'synthetic-v1'})
    out = Path(destination)
    if out.exists():
        raise ValueError('use a new output directory; dataset versions must not be overwritten')
    out.mkdir(parents=True)
    for name, samples in result.items():
        (out / (name + '.jsonl')).write_text(''.join(json.dumps(s, ensure_ascii=False) + '\n' for s in samples))
    (out / 'manifest.json').write_text(json.dumps(manifest, indent=2))
    return {'accepted': len(accepted), 'skipped': len(skipped),
            'splits': {name: len(samples) for name, samples in result.items()}}


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('source')
    parser.add_argument('destination')
    args = parser.parse_args()
    print(json.dumps(build(args.source, args.destination), indent=2))
