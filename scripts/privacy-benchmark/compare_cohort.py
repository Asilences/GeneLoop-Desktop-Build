"""Frozen retrospective cohort check before a full rule-revision benchmark.

Uses the existing official Presidio/nervaluate evaluation adapters. Gold never
enters recognition. Aggregate output excludes text, file names and secret values.
"""
import argparse
from collections import Counter,defaultdict
from concurrent.futures import ProcessPoolExecutor
import hashlib
import json
from pathlib import Path
import time

import run_pii as bench


def coverage(row):
    covered={i for p in row['core']['pred'] for i in range(p['start'],p['end'])}
    return [set(range(s['start'],s['end']))<=covered for s in row['gold']]


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    for name in ('inputs','gold','config','baseline-results','output'):
        parser.add_argument('--'+name,type=Path,required=True)
    parser.add_argument('--workers',type=int,required=True)
    args=parser.parse_args();args.output.mkdir(mode=0o700,parents=True,exist_ok=False)
    started=time.perf_counter();config=json.loads(args.config.read_text())
    from src.adapters.rsi_privacy_policy import POLICY_SHA256
    assert config['privacy_policy_sha256']==POLICY_SHA256
    inputs=[r for r in map(json.loads,args.inputs.read_text().splitlines()) if r['phase']!='semantic_control']
    gold={(r['dataset'],r['id']):r['gold'] for r in map(json.loads,args.gold.read_text().splitlines())}
    assert len(inputs)==len(gold)==600 and len({(r['dataset'],r['id']) for r in inputs})==600
    records=[dict(row,gold=gold[row['dataset'],row['id']]) for row in inputs]
    baseline={}
    for dataset in ('zh_formal','zh_chat','en_test'):
        for row in map(json.loads,(args.baseline_results/(dataset+'-records.jsonl')).read_text().splitlines()):
            if (row['dataset'],row['id']) in gold:baseline[row['dataset'],row['id']]=row
    assert baseline.keys()==gold.keys()
    rows=[]
    with ProcessPoolExecutor(max_workers=args.workers,initializer=bench.initialize,initargs=(str(args.config),)) as pool:
        with (args.output/'records-private.jsonl').open('w') as stream:
            for index,row in enumerate(pool.map(bench.evaluate_record,records,chunksize=1),1):
                rows.append(row);stream.write(json.dumps(row)+'\n')
                if index%50==0:stream.flush();print(json.dumps({'completed':index,'total':600}),flush=True)
    summary={'purpose':'retrospective development cohort; not an independent holdout or full benchmark',
        'policy_sha256':POLICY_SHA256,'config_sha256':hashlib.sha256(args.config.read_bytes()).hexdigest(),
        'inputs_sha256':hashlib.sha256(args.inputs.read_bytes()).hexdigest(),
        'gold_sha256':hashlib.sha256(args.gold.read_bytes()).hexdigest(),'rows':len(rows),'workers':args.workers,
        'source_sha256':hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),'datasets':{}}
    for dataset in ('zh_formal','zh_chat','en_test'):
        selected=[r for r in rows if r['dataset']==dataset];types=defaultdict(Counter);stats=Counter()
        for row in selected:
            prior=baseline[row['dataset'],row['id']];assert row['gold']==prior['gold'] and row['chars']==prior['chars']
            before,after=coverage(prior),coverage(row)
            for span,was,now in zip(row['gold'],before,after):
                types[span['label']].update(gold_entities=1,r3_covered=int(was),candidate_covered=int(now),
                    gained=int(now and not was),lost=int(was and not now))
            stats.update(native_changed_records=int(row['native']['pred']!=prior['native']['pred']),
                r3_non_pii_masked=prior['core']['chars']['masked_non_pii_chars'],
                candidate_non_pii_masked=row['core']['chars']['masked_non_pii_chars'],
                non_pii_chars=row['core']['chars']['non_pii_chars'],
                r3_context_chunks=prior['core']['retained_context_chunks'],
                candidate_context_chunks=row['core']['retained_context_chunks'],context_chunks=row['core']['context_chunks'])
        bench.CONFIG=config
        summary['datasets'][dataset]={'rows':len(selected),'delta':dict(stats),
            'by_gold_type':{name:dict(value) for name,value in types.items()},'candidate':bench.summarize(selected,{})}
    summary.update(wall_seconds=time.perf_counter()-started,cloud_requests=0,production_service_touched=False)
    (args.output/'summary.json').write_text(json.dumps(summary,indent=2))
    print(json.dumps({'completed':True,'rows':len(rows)}))


if __name__=='__main__':main()
