"""Aggregate frozen R2/R3 comparisons without exporting per-record material."""
import argparse
from collections import Counter, defaultdict
import hashlib
import json
from pathlib import Path


def load(path):
    return json.loads(path.read_text())


def records(path, field):
    rows=[json.loads(line) for line in path.read_text().splitlines()]
    indexed={row[field]:row for row in rows}
    assert len(rows)==len(indexed)
    return indexed


def coverage(row, engine='core'):
    covered={i for span in row[engine]['pred'] for i in range(span['start'],span['end'])}
    result=defaultdict(Counter)
    for span in row['gold']:
        result[span['label']].update(gold_entities=1,fully_covered_entities=int(set(range(span['start'],span['end']))<=covered))
    return {k:dict(v) for k,v in result.items()}


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--r2',type=Path,required=True)
    parser.add_argument('--r3',type=Path,required=True)
    parser.add_argument('--ablation',type=Path,required=True)
    parser.add_argument('--output',type=Path,required=True)
    args=parser.parse_args()
    assert not args.output.exists()
    summary={'independent_unseen_evaluation':False,'pii':{},'credentials':{},'actual_core_matches_frozen_union_ablation':True,
        'source_sha256':hashlib.sha256(Path(__file__).read_bytes()).hexdigest()}
    for dataset in ('zh_formal','zh_chat','en_test'):
        old=records(args.r2/'pii-r2'/f'{dataset}-records.jsonl','id')
        new=records(args.r3/'pii-r3'/f'{dataset}-records.jsonl','id')
        ablation=records(args.ablation/f'{dataset}-private.jsonl','id')
        assert old.keys()==new.keys()==ablation.keys()
        transitions=Counter();by_type=defaultdict(Counter);native_types=defaultdict(Counter);cohort=Counter();changed=Counter()
        for key,row in new.items():
            prior=old[key]
            assert prior['gold']==row['gold'] and prior['chars']==row['chars']
            assert prior['native']['pred']==row['native']['pred'], 'native_baseline_drift'
            expected=ablation[key]['variants']['union_person_views']
            assert row['core']['chars']==expected['chars']
            assert row['core']['retained_context_chunks']==expected['retained_context_chunks']
            types=coverage(row)
            for label,counts in coverage(row,'native').items():
                native_types[label].update(counts)
            assert all(types[label]['fully_covered_entities']==item['fully_covered_entities'] for label,item in expected['by_gold_type'].items())
            a,b=prior['module'],row['module']
            transitions[str(a['accepted'])+'_to_'+str(b['accepted'])]+=1
            if a['accepted'] and b['accepted']:
                assert a['gold_entities']==b['gold_entities']
                cohort.update(documents=1,gold_entities=b['gold_entities'],r2_literal_residuals=a['literal_residual_entities'],r3_literal_residuals=b['literal_residual_entities'])
            for label,counts in expected['by_gold_type'].items():
                by_type[label].update(counts)
            changed.update(changed_core_predictions=int(prior['core']['pred']!=row['core']['pred']))
        summary['pii'][dataset]={'records':len(new),'admission_transitions':dict(transitions),
            'same_admitted_cohort':dict(cohort),'by_gold_type':{k:dict(v) for k,v in by_type.items()},
            'native_by_gold_type':{k:dict(v) for k,v in native_types.items()},**dict(changed)}
    old=records(args.r2/'credentials-r2-budget120/module-file-records-private.jsonl','file')
    new=records(args.r3/'credentials-r3-budget120/module-file-records-private.jsonl','file')
    assert old.keys()==new.keys() and len(new)==11030
    status=Counter();cohort=Counter();native_risk=0
    for key,row in new.items():
        prior=old[key]
        assert prior['truth']==row['truth'] and prior['gitleaks_flagged']==row['gitleaks_flagged']
        status[prior['status']+'_to_'+row['status']]+=1
        if prior['accepted'] is True and row['accepted'] is True:
            assert prior['extractable_positive_rows']==row['extractable_positive_rows']
            cohort.update(files=1,extractable_positive_rows=row['extractable_positive_rows'],r2_literal_residuals=prior['literal_residual_rows'],r3_literal_residuals=row['literal_residual_rows'])
        native_risk+=int(row['accepted'] is True and row['gitleaks_flagged'] and row.get('any_literal_residual',False))
    summary['credentials']={'files':11030,'status_transitions':dict(status),'same_admitted_cohort':dict(cohort),
        'native_flagged_accepted_files_with_literal_residual':native_risk}
    args.output.write_text(json.dumps(summary,indent=2))
    print(json.dumps({'pii_records':sum(item['records'] for item in summary['pii'].values()),'credential_files':len(new),'actual_core_matches_ablation':True}))


if __name__=='__main__':
    main()
