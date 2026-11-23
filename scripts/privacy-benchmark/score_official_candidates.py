"""Score official candidate spans against frozen gold, separately from inference."""
import argparse
from collections import Counter
import hashlib
import json
from pathlib import Path

import run_pii as bench
from score_model_candidates import aggregate, render


def key(row):
    return row['dataset'], row['id']


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    for name in ('config','comparison','inputs','gold','baseline-results','candidate-output','semantic-controls','output'):
        parser.add_argument('--'+name,type=Path,required=True)
    args=parser.parse_args()
    assert not args.output.exists()
    bench.initialize(str(args.config))
    comparison=json.loads(args.comparison.read_text())
    inputs={key(row):row for row in map(json.loads,args.inputs.read_text().splitlines())}
    gold={key(row):row['gold'] for row in map(json.loads,args.gold.read_text().splitlines())}
    controls=json.loads(args.semantic_controls.read_text())
    manifest=json.loads((args.candidate_output/'manifest.json').read_text())
    assert manifest['inputs_sha256']==hashlib.sha256(args.inputs.read_bytes()).hexdigest()
    predictions={key(row):row for row in map(json.loads,(args.candidate_output/'predictions-private.jsonl').read_text().splitlines())}
    assert predictions.keys()==inputs.keys()
    baseline={}
    for dataset in ('zh_formal','zh_chat','en_test'):
        for row in map(json.loads,(args.baseline_results/f'{dataset}-records.jsonl').read_text().splitlines()):
            if key(row) in gold:
                assert row['gold']==gold[key(row)]
                baseline[key(row)]=row['core']['pred']
    assert baseline.keys()==gold.keys()
    from src.adapters.rsi_text_privacy import anonymize_text
    for control in controls:
        bench.CAPTURE.clear();bench.CAPTURE_ENABLED=True
        try:
            anonymize_text(inputs[key(control)]['text'])
            baseline[key(control)]=bench.CAPTURE[-1][1] if bench.CAPTURE else []
        finally:
            bench.CAPTURE_ENABLED=False
    result={'manifest':manifest,'baseline_name':'r4','gold_passed_to_detector':False,
            'independent_unseen_evaluation':False,'scope':'text span replay; full public admission is verified separately',
            'scorer_sha256':hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),'groups':{},'semantics':{}}
    total_gains=total_losses=0;non_pii_ok=context_ok=True
    for dataset in ('zh_formal','zh_chat','en_test'):
        selected=[row for row in inputs.values() if row['dataset']==dataset and key(row) in gold]
        available=[dict(row,gold=gold[key(row)]) for row in selected if not predictions[key(row)]['error']]
        old=[baseline[key(row)] for row in available]
        scoped=[predictions[key(row)]['pred'] for row in available]
        native=[predictions[key(row)]['native_pred'] for row in available]
        union=[a+b for a,b in zip(old,scoped)]
        group={'total':len(selected),'available':len(available),
               'errors':dict(Counter(predictions[key(row)]['error'] for row in selected if predictions[key(row)]['error']))}
        for name,pred in [('r4',old),('native_opf_all_labels',native),('policy_scoped_opf',scoped),('r4_plus_opf',union)]:
            group[name]=aggregate(available,pred,old,'r4')
        a,b=group['r4'],group['r4_plus_opf']
        added=(b['characters']['masked_non_pii_chars']-a['characters']['masked_non_pii_chars'])/max(1,a['characters']['non_pii_chars'])*100
        drop=(a['retained_context_chunks']-b['retained_context_chunks'])/max(1,a['context_chunks'])*100
        group['added_non_pii_masking_percentage_points']=added
        group['context_retention_drop_percentage_points']=drop
        total_gains+=sum(x['gained_over_r4'] for x in b['by_gold_type'].values())
        total_losses+=sum(x['lost_from_r4'] for x in b['by_gold_type'].values())
        non_pii_ok &= added <= comparison['adoption_gates']['max_added_non_pii_masking_percentage_points']
        context_ok &= drop <= comparison['adoption_gates']['max_context_retention_drop_percentage_points']
        group['native_credsweeper_flagged']=sum(predictions[key(row)].get('credential_findings',0)>0 for row in available)
        result['groups'][dataset]=group
    for mode in ('r4','native_opf_all_labels','policy_scoped_opf','r4_plus_opf'):
        metrics=Counter();errors=Counter()
        for control in controls:
            source=inputs[key(control)]['text'];prediction=predictions[key(control)]
            if prediction['error']:
                errors[prediction['error']]+=1;continue
            pred=(baseline[key(control)] if mode=='r4' else prediction['native_pred'] if mode=='native_opf_all_labels'
                  else prediction['pred'] if mode=='policy_scoped_opf' else baseline[key(control)]+prediction['pred'])
            output,_=render(source,pred)
            metrics.update(rows=1,invariants=len(control['keep']),retained_invariants=sum(value in output for value in control['keep']),
                           sensitive_values=len(control['sensitive']),literal_residuals=sum(value in output for value in control['sensitive']))
        result['semantics'][mode]=dict(metrics,unknown=dict(errors))
    sem=result['semantics']['r4_plus_opf']
    gates={'available_all_inputs':sum(not row['error'] for row in predictions.values())==len(inputs),
           'no_old_full_coverage_lost':total_losses==0,'coverage_improved':total_gains>0,
           'added_non_pii_within_gate':non_pii_ok,'context_retention_within_gate':context_ok,
           'all_task_requirements_retained':sem.get('retained_invariants')==comparison['adoption_gates']['required_retained_semantic_invariants']}
    result['adoption']={'text_layer_gates':gates,'all_text_layer_gates_passed':all(gates.values()),
                        'newly_fully_covered_entities':total_gains,'previously_fully_covered_lost':total_losses,
                        'default_adopted':False,'remaining':'full public admission, independent new sources, and product validation'}
    args.output.write_text(json.dumps(result,indent=2))
    print(json.dumps(result['adoption']),flush=True)


if __name__=='__main__':main()
