"""Offline evidence index. Never modify original attempts or call a provider."""
import argparse
import json
from pathlib import Path
import sys

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
from src.adapters.capability_construction_history import capture,build_history
from src.adapters.capability_feedback import file_ref
from src.adapters.capability_improvement import evidence,save


def inspect(manifest, output):
    """Host manifest supplies pinned snapshots and optional publication outcomes."""
    output=Path(output);output.mkdir(parents=True,exist_ok=False,mode=0o700)
    evidence(manifest['task']);records=[]
    save(output/'manifest.json',manifest)
    for index,row in enumerate(manifest['attempts']):
        snapshot=json.loads(evidence(row['snapshot']))
        outcome=json.loads(evidence(row['verification'])) if row.get('verification') else None
        directory=Path(row['directory'])
        candidate=json.loads((directory/'candidate.json').read_text(encoding='utf-8')) if (directory/'candidate.json').is_file() else None
        records.append(capture({'id':manifest['goal_id'],'task':manifest['task']},directory,snapshot,
            candidate,outcome,output=output/f'attempt-{index}.json'))
    view=build_history(records,manifest['task']);save(output/'history.json',view)
    return file_ref(output/'history.json')


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--manifest',type=Path,required=True)
    parser.add_argument('--output',type=Path,required=True)
    args=parser.parse_args()
    if not args.output.resolve().is_relative_to(ROOT/'.local'):
        parser.error('construction evidence must remain in private .local')
    print(json.dumps(inspect(json.loads(args.manifest.read_text(encoding='utf-8')),args.output)))
