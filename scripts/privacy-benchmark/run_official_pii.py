"""Full PII benchmark using the public contract and genuine optional detectors.

Reuses frozen loading, rendering observation, and nervaluate scoring. The native
Gitleaks measurement remains separate from the additional credential scanner.
"""
import argparse
from collections import Counter, defaultdict
from concurrent.futures import FIRST_COMPLETED, TimeoutError, wait
import hashlib
import json
from pathlib import Path
import sys
import time

from pebble import ProcessPool
import run_pii as bench

BACKEND=None
RAW_OPF=None
CURRENT_TEXT=None
ACTUAL_OPF_CALLS=0
REUSED_OPF_PREDICTIONS=0


def initialize(repo, protocol, settings, gpu_devices=None):
    global BACKEND
    from gpu_workers import select_worker_gpu
    select_worker_gpu(gpu_devices)
    sys.path.insert(0,repo)
    bench.initialize(protocol)
    if settings.get('format') == 'geneloop.privacy-chinese/v1':
        from src.adapters.rsi_chinese_privacy import ChineseTools
        BACKEND=ChineseTools(settings)
        return
    from src.adapters import rsi_text_privacy as text_privacy
    from src.adapters.rsi_privacy_candidates import OfficialTools
    BACKEND=OfficialTools(settings)
    original=BACKEND.native_findings
    def observed(text):
        global RAW_OPF,ACTUAL_OPF_CALLS,REUSED_OPF_PREDICTIONS
        # The native/core/public views of one observation use the same stateless
        # classifier on the same exact string. Reuse only this freshly computed
        # prediction; otherwise the evaluation budget charges inference twice.
        # No prior run, other record, normalized string or different field hits.
        if text==CURRENT_TEXT and RAW_OPF is not None:
            REUSED_OPF_PREDICTIONS+=1
            return [dict(span) for span in RAW_OPF]
        spans=original(text)
        ACTUAL_OPF_CALLS+=1
        if text==CURRENT_TEXT and RAW_OPF is None:
            RAW_OPF=spans
        return spans
    BACKEND.native_findings=observed
    # evaluate_record imports this name for the native Gitleaks measurement.
    # privacy._scan already refers to the full scan wrapper through its frozen
    # observer, so actual public admission still invokes both selected tools.
    text_privacy._scan=text_privacy._scan_gitleaks


def evaluate(record):
    global RAW_OPF,CURRENT_TEXT,ACTUAL_OPF_CALLS,REUSED_OPF_PREDICTIONS
    from src.adapters.rsi_privacy_candidates import candidate_context
    from score_model_candidates import render
    RAW_OPF=None;CURRENT_TEXT=record['text'];ACTUAL_OPF_CALLS=0;REUSED_OPF_PREDICTIONS=0
    started=time.perf_counter()
    try:
        with candidate_context(BACKEND):
            row=bench.evaluate_record(record)
        if getattr(BACKEND,'detector',None) is not None and RAW_OPF is not None:
            all_mapping={'private_person':'PERSON','private_address':'LOCATION','private_email':'EMAIL_ADDRESS',
                         'private_phone':'PHONE_NUMBER','private_url':'PRIVATE_REFERENCE','private_date':'DATE_TIME',
                         'account_number':'FINANCIAL_ACCOUNT','secret':'CREDENTIAL'}
            raw=[dict(span,label=all_mapping[span['label']]) for span in RAW_OPF]
            output,operations=render(record['text'],raw)
            chunks=bench.context_chunks(record['text'],record['gold'],bench.CONFIG['semantics_proxy_min_non_pii_chunk_chars'])
            row['official_opf']={'pred':operations,'error_type':None,
                'chars':bench.character_metrics(record['text'],record['gold'],operations),
                'context_chunks':len(chunks),'retained_context_chunks':sum(chunk in output for chunk in chunks)}
        else:
            enabled=getattr(BACKEND,'detector',None) is not None
            row['official_opf']={'enabled':enabled,'error_type':'no_complete_model_prediction' if enabled else 'not_enabled'}
        if getattr(BACKEND,'scanner',None) is not None:
            try:
                row['native_credsweeper']={'flagged':BACKEND.credential_count(record['text'])>0,'error':False,'enabled':True}
            except Exception as error:
                row['native_credsweeper']={'error':True,'error_type':type(error).__name__,'enabled':True}
        else:
            row['native_credsweeper']={'error':False,'enabled':False}
        row['total_observation_seconds']=time.perf_counter()-started
        row['actual_opf_calls']=ACTUAL_OPF_CALLS
        row['same_record_prediction_reuses']=REUSED_OPF_PREDICTIONS
        return row
    finally:
        RAW_OPF=None;CURRENT_TEXT=None


def compare_coverage(rows, baseline_path):
    baseline={row['id']:row for row in map(json.loads,baseline_path.read_text().splitlines())}
    types=defaultdict(Counter)
    for row in rows:
        old=baseline[row['id']]
        assert old['gold']==row['gold']
        if old.get('evaluation_status','completed')!='completed' or 'core' not in old:
            continue  # An unknown baseline is not an observed zero-coverage result.
        before={i for s in old['core']['pred'] for i in range(s['start'],s['end'])}
        after={i for s in row['core']['pred'] for i in range(s['start'],s['end'])}
        for span in row['gold']:
            indices=set(range(span['start'],span['end']))
            a,b=indices<=before,indices<=after
            types[span['label']].update(gold_entities=1,old_fully_covered=int(a),fully_covered=int(b),gained=int(b and not a),lost=int(a and not b))
    return {key:dict(value) for key,value in types.items()}


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    for name in ('repo','root','config','settings','baseline-results','output'):
        parser.add_argument('--'+name,type=Path,required=True)
    parser.add_argument('--workers',type=int,required=True)
    parser.add_argument('--limit-per-dataset',type=int)
    parser.add_argument('--gpu-devices',help='Explicit physical device cycle for isolated workers, e.g. 0,1,2,3')
    args=parser.parse_args()
    assert not args.output.exists()
    args.output.mkdir(mode=0o700,parents=True)
    config=json.loads(args.config.read_text());settings=json.loads(args.settings.read_text())
    bench.CONFIG=config
    snapshot={'protocol_sha256':hashlib.sha256(args.config.read_bytes()).hexdigest(),'protocol':config,
              'settings_sha256':hashlib.sha256(args.settings.read_bytes()).hexdigest(),
              'driver_sha256':hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
              'candidate_manifest_sha256':hashlib.sha256((args.repo/'config/rsi-privacy-candidate-tools.json').read_bytes()).hexdigest(),
              'cloud_requests':0,'gold_passed_to_official_detector':False,'datasets':{},'workers':args.workers,
              'pilot_limit_per_dataset':args.limit_per_dataset,
              'same_record_prediction_reuse':'only freshly computed OPF spans for the exact same document across metric views; no reuse across records or old runs',
              'module_timing_scope':'measurement can reuse the native prediction; not standalone public admission latency, which is measured separately',
              'deadline_scope':'120 seconds per combined evaluation observation; warm initialization separate; unknown never safe'}
    snapshot['backend_format']=settings['format']
    if settings['format']=='geneloop.privacy-chinese/v1':
        snapshot['chinese_manifest_sha256']=hashlib.sha256((args.repo/'config/rsi-privacy-chinese-tools.json').read_bytes()).hexdigest()
        snapshot['module_timing_scope']='standalone public admission within the worker; Chinese predictions are not reused across metric views'
        snapshot['same_record_prediction_reuse']='disabled for Chinese backend; same frozen inputs, no old prediction reuse'
    for dataset in ('zh_formal','zh_chat','en_test'):
        records,audit=bench.load_records(args.root,dataset,config)
        corpus_rows=len(records)
        corpus_gold=sum(len(r['gold']) for r in records)
        if args.limit_per_dataset is not None:
            assert args.limit_per_dataset>0
            records=records[:args.limit_per_dataset]
        started=time.perf_counter();pending={};todo=iter(records);rows=[];statuses=Counter()
        with (args.output/f'{dataset}-records.jsonl').open('w') as stream, ProcessPool(
                max_workers=args.workers,initializer=initialize,
                initargs=(str(args.repo.resolve()),str(args.config.resolve()),settings,args.gpu_devices)) as pool:
            def submit():
                try:record=next(todo)
                except StopIteration:return
                future=pool.schedule(evaluate,args=(record,),timeout=120)
                pending[future]=record
            for _ in range(args.workers):submit()
            while pending:
                ready,_=wait(pending,return_when=FIRST_COMPLETED)
                for future in ready:
                    record=pending.pop(future)
                    try:row=future.result()
                    except TimeoutError:
                        row={k:record[k] for k in ('id','dataset','gold')};row['evaluation_status']='evaluation_timeout'
                    except Exception as error:
                        row={k:record[k] for k in ('id','dataset','gold')};row.update(evaluation_status='evaluation_error',error_type=type(error).__name__)
                    row.setdefault('evaluation_status','completed')
                    rows.append(row);statuses[row['evaluation_status']]+=1
                    stream.write(json.dumps(row,ensure_ascii=False)+'\n');stream.flush()
                    if len(rows)%250==0 or len(rows)==len(records):
                        print(json.dumps({'dataset':dataset,'completed':len(rows),'total':len(records),'statuses':dict(statuses),'seconds':time.perf_counter()-started}),flush=True)
                    submit()
        assert len(rows)==len(records)
        completed=[r for r in rows if r['evaluation_status']=='completed']
        summary=bench.summarize(completed,audit) if completed else {}
        summary.update(full_corpus_rows=corpus_rows,total_rows=len(rows),completed_rows=len(completed),evaluation_statuses=dict(statuses),wall_seconds=time.perf_counter()-started,
                       full_corpus_gold_entities=corpus_gold,evaluated_gold_entities=sum(len(r['gold']) for r in records),
                       unknown_gold_entities=sum(len(r['gold']) for r in rows if r['evaluation_status']!='completed'))
        summary['r4_same_completed_coverage']=compare_coverage(completed,args.baseline_results/f'{dataset}-records.jsonl')
        opf=[r for r in completed if not r['official_opf']['error_type']]
        summary['official_opf']={'available':len(opf),'unavailable':len(completed)-len(opf),
            'enabled':settings['format']!='geneloop.privacy-chinese/v1' and settings.get('text_mode')=='r4+opf',
            'characters':dict(sum((Counter(r['official_opf']['chars']) for r in opf),Counter())),
            'standard_scores':bench.standard_scores([r['gold'] for r in opf],[r['official_opf']['pred'] for r in opf]) if opf else None,
            'context_chunks':sum(r['official_opf']['context_chunks'] for r in opf),
            'retained_context_chunks':sum(r['official_opf']['retained_context_chunks'] for r in opf)}
        summary['native_credsweeper']={'flagged':sum(r['native_credsweeper'].get('flagged',False) for r in completed),
                                       'enabled_observations':sum(r['native_credsweeper'].get('enabled',True) for r in completed),
                                       'errors':sum(r['native_credsweeper']['error'] for r in completed)}
        snapshot['datasets'][dataset]=summary
        (args.output/'pii-summary.json').write_text(json.dumps(snapshot,indent=2))
    print(json.dumps({'finished':True,'datasets':{k:v['evaluation_statuses'] for k,v in snapshot['datasets'].items()}}),flush=True)


if __name__=='__main__':main()
