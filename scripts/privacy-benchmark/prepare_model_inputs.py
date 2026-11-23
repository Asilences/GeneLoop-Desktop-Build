"""Deterministic retrospective candidate split; gold is a separate private file."""
import argparse
import hashlib
import json
from pathlib import Path

import run_pii as bench


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--root',type=Path,required=True)
    parser.add_argument('--protocol',type=Path,required=True)
    parser.add_argument('--comparison',type=Path,required=True)
    parser.add_argument('--semantics',type=Path,required=True)
    parser.add_argument('--output',type=Path,required=True)
    args=parser.parse_args()
    args.output.mkdir(mode=0o700,parents=True,exist_ok=False)
    protocol=json.loads(args.protocol.read_text(encoding='utf-8'))
    config=json.loads(args.comparison.read_text(encoding='utf-8'))
    selection=config['selection'];inputs=[];gold=[];controls=[]
    for dataset in ('zh_formal','zh_chat','en_test'):
        rows,_=bench.load_records(args.root,dataset,protocol)
        rows=sorted(rows,key=lambda row:hashlib.sha256(f"{selection['seed']}:{dataset}:{row['id']}".encode()).hexdigest())[:selection['per_dataset']]
        assert len(rows)==selection['development']+selection['confirmation']
        for index,row in enumerate(rows):
            phase='development' if index<selection['development'] else 'confirmation'
            inputs.append({k:row[k] for k in ('id','dataset','text')}|{'phase':phase})
            gold.append({k:row[k] for k in ('id','dataset','gold')}|{'phase':phase})
    cases=json.loads(args.semantics.read_text(encoding='utf-8'))
    for intent in cases['intents']:
        for variant in cases['variants']:
            text=intent['text']+(cases['inline_identity'] if variant=='inline_identity' else '')
            dataset='zh_semantics' if any('\u4e00'<=c<='\u9fff' for c in text) else 'en_semantics'
            key=intent['id']+':'+variant
            inputs.append({'id':key,'dataset':dataset,'text':text,'phase':'semantic_control'})
            controls.append({'id':key,'dataset':dataset,'keep':intent['keep'],
                'sensitive':cases['inline_sensitive_values'] if variant=='inline_identity' else [],
                'scope':'text layer only; structured fields remain handled by common module'})
    for name,rows in [('inputs-private.jsonl',inputs),('gold-private.jsonl',gold)]:
        (args.output/name).write_text(''.join(json.dumps(row,ensure_ascii=False)+'\n' for row in rows),encoding='utf-8')
    (args.output/'semantic-controls-private.json').write_text(json.dumps(controls),encoding='utf-8')
    manifest={'pii_records':len(gold),'semantic_controls':len(controls),'gold_passed_to_detector':False,
        'independent_unseen_evaluation':False,'selection':selection,'config_sha256':hashlib.sha256(args.comparison.read_bytes()).hexdigest(),
        'files_sha256':{p.name:hashlib.sha256(p.read_bytes()).hexdigest() for p in args.output.iterdir()}}
    (args.output/'manifest.json').write_text(json.dumps(manifest,indent=2),encoding='utf-8')
    print(json.dumps({'pii_records':len(gold),'semantic_controls':len(controls)}))


if __name__=='__main__':
    main()
