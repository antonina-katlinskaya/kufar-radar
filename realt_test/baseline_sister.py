"""Establish one safe no-send baseline before Realt sister notifications are resumed."""
import json
from pathlib import Path
from realt_test.github_store import GitHubState
from realt_test.notify import initialize_sister_baseline, BASELINE_V2_KEY

def main():
    report=Path('realt_test/results.json')
    if not report.exists():
        raise RuntimeError('Realt audit result missing; cannot initialize sister baseline')
    result=json.loads(report.read_text(encoding='utf-8'))
    db=GitHubState()
    installed=initialize_sister_baseline(db,result)
    print(json.dumps({'baseline_created':installed,'delivery_enabled':False,
                      'baseline_key':BASELINE_V2_KEY,'telegram_sent':False}))

if __name__ == '__main__':
    main()
