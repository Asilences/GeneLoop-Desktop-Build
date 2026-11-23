"""Score offline candidate spans with the frozen Presidio/nervaluate adapters.

Never calls a candidate model. Private inputs/gold/predictions remain local;
only aggregate counts and source hashes are written to the public summary.
"""
import argparse
from collections import Counter, defaultdict
import hashlib
import json
from pathlib import Path

import run_pii as bench


def key(row):
    return row['dataset'], row['id']


def render(text, spans):
    from presidio_analyzer import RecognizerResult
    bench.CAPTURE.clear()
    bench.CAPTURE_ENABLED = True
    try:
        output = bench.ANONYMIZER.anonymize(text=text, analyzer_results=[
            RecognizerResult(entity_type=s['label'], start=s['start'], end=s['end'], score=.9) for s in spans]).text
        operations = bench.CAPTURE[-1][1] if bench.CAPTURE else []
    finally:
        bench.CAPTURE_ENABLED = False
    return output, operations


def aggregate(rows, predictions, baseline, baseline_name='r2'):
    chars = Counter()
    types = defaultdict(Counter)
    gold, guesses = [], []
    chunks = retained = 0
    for row, pred, old in zip(rows, predictions, baseline):
        output, ops = render(row['text'], pred)
        gold.append(row['gold']); guesses.append(ops)
        chars.update(bench.character_metrics(row['text'], row['gold'], ops))
        covered = {i for s in ops for i in range(s['start'], s['end'])}
        before = {i for s in old for i in range(s['start'], s['end'])}
        for span in row['gold']:
            indices = set(range(span['start'], span['end']))
            now, prior = indices <= covered, indices <= before
            types[span['label']].update({'gold_entities': 1, 'fully_covered_entities': int(now),
                'gained_over_'+baseline_name: int(now and not prior),
                'lost_from_'+baseline_name: int(prior and not now)})
        context = bench.context_chunks(row['text'], row['gold'], bench.CONFIG['semantics_proxy_min_non_pii_chunk_chars'])
        chunks += len(context); retained += sum(value in output for value in context)
    scope = set(bench.CONFIG['supported_text_tags'])
    return {'rows':len(rows), 'characters':dict(chars), 'by_gold_type':{k:dict(v) for k,v in types.items()},
        'context_chunks':chunks, 'retained_context_chunks':retained,
        'full_taxonomy':bench.standard_scores(gold,guesses),
        'declared_scope':bench.standard_scores([[s for s in row if s['label'] in scope] for row in gold],
                                             [[s for s in row if s['label'] in scope] for row in guesses])}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--config',type=Path,required=True)
    parser.add_argument('--inputs',type=Path,required=True)
    parser.add_argument('--gold',type=Path,required=True)
    parser.add_argument('--r2-results','--baseline-results',dest='r2_results',type=Path,required=True)
    parser.add_argument('--baseline-name',choices=('r2','r3','r4_context'),default='r2')
    parser.add_argument('--candidate-results',type=Path,nargs='+',required=True)
    parser.add_argument('--semantic-controls',type=Path,required=True)
    parser.add_argument('--output',type=Path,required=True)
    args=parser.parse_args()
    assert not args.output.exists()
    bench.initialize(str(args.config))
    inputs={key(row):row for row in map(json.loads,args.inputs.read_text().splitlines())}
    gold={key(row):row['gold'] for row in map(json.loads,args.gold.read_text().splitlines())}
    baseline={}
    for name in ('zh_formal','zh_chat','en_test'):
        for row in map(json.loads,(args.r2_results/f'{name}-records.jsonl').read_text().splitlines()):
            if key(row) in inputs:
                assert row['gold']==gold[key(row)]
                baseline[key(row)]=row['core']['pred']
    assert len(gold)==len(baseline)==600 and len(inputs)==624
    controls=json.loads(args.semantic_controls.read_text())
    from src.adapters.rsi_text_privacy import anonymize_text
    for control in controls:
        source=inputs[key(control)]['text']
        bench.CAPTURE.clear();bench.CAPTURE_ENABLED=True
        try:
            anonymize_text(source)
            baseline[key(control)]=bench.CAPTURE[-1][1] if bench.CAPTURE else []
        finally:
            bench.CAPTURE_ENABLED=False
    summary={'evaluation':'retrospective-600-PII-and-24-semantic-controls','independent_unseen_evaluation':False,
        'gold_passed_to_detector':False,'text_layer_only':True,'unknown_is_safe_or_rejected':False,
        'baseline_name':args.baseline_name,
        'config_sha256':hashlib.sha256(args.config.read_bytes()).hexdigest(),
        'inputs_sha256':hashlib.sha256(args.inputs.read_bytes()).hexdigest(),
        'scorer_sha256':hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),'candidates':{}}
    for folder in args.candidate_results:
        manifest=json.loads((folder/'manifest.json').read_text())
        assert manifest['inputs_sha256']==summary['inputs_sha256']
        name=manifest['candidate']
        if manifest.get('load_error'):
            summary['candidates'][name]={'load_error':manifest['load_error'],'available_rows':0,'total':624}
            continue
        predictions={key(row):row for row in map(json.loads,(folder/'predictions-private.jsonl').read_text().splitlines())}
        assert predictions.keys()==inputs.keys() and len(predictions)==624
        result={'sources':manifest['sources'],'versions':manifest['versions'],'load_seconds':manifest['load_seconds'],
            'loading':manifest['loading'],'status_counts':manifest['status_counts'],
            'runner_sha256':manifest['runner_sha256'],'comparison_config_sha256':manifest['config_sha256'],
            'inputs_sha256':manifest['inputs_sha256'],'groups':{},'semantics':{}}
        if manifest.get('receipt_recovery'):
            result['receipt_recovery']=manifest['receipt_recovery']
            result['loading_validation_seconds']=manifest['loading_validation_seconds']
        for dataset in ('zh_formal','zh_chat','en_test'):
            for phase in ('development','confirmation'):
                selected=[row for row in inputs.values() if row['dataset']==dataset and row['phase']==phase]
                available=[dict(row,gold=gold[key(row)]) for row in selected if not predictions[key(row)]['error']]
                old=[baseline[key(row)] for row in available]
                pred=[predictions[key(row)]['pred'] for row in available]
                result['groups'][dataset+':'+phase]={'total':len(selected),'available':len(available),
                    'unknown':dict(Counter(predictions[key(row)]['error'] for row in selected if predictions[key(row)]['error'])),
                    'timing':bench.timing([predictions[key(row)]['seconds'] for row in selected]),
                    args.baseline_name+'_same_available_cohort':aggregate(available,old,old,args.baseline_name),
                    'model_only':aggregate(available,pred,old,args.baseline_name),
                    args.baseline_name+'_plus_model':aggregate(available,[a+b for a,b in zip(old,pred)],old,args.baseline_name)}
        for mode in (args.baseline_name,'model_only',args.baseline_name+'_plus_model'):
            metrics=Counter();errors=Counter()
            for control in controls:
                original=inputs[key(control)]['text'];p=predictions[key(control)]
                if p['error']:
                    errors[p['error']]+=1;continue
                pred=(baseline[key(control)] if mode==args.baseline_name else p['pred'] if mode=='model_only' else baseline[key(control)]+p['pred'])
                output,_=render(original,pred)
                metrics.update(rows=1,invariants=len(control['keep']),retained_invariants=sum(value in output for value in control['keep']),
                    sensitive_values=len(control['sensitive']),literal_residuals=sum(value in output for value in control['sensitive']))
            result['semantics'][mode]=dict(metrics,unknown=dict(errors),scope='text only; structured identity fields are not submitted to candidate')
        summary['candidates'][name]=result
    args.output.write_text(json.dumps(summary,indent=2))
    print(json.dumps({name:result.get('status_counts',result) for name,result in summary['candidates'].items()}))


if __name__=='__main__':
    main()
