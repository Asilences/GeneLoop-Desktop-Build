"""Compare frozen complete runs on identical gold and admission cohorts.

No detector calls and no private text/paths in aggregate output. Refusal and
unknown transitions remain distinct from measured residual reduction.
"""
import argparse
from collections import Counter, defaultdict
import hashlib
import json
from pathlib import Path


def records(path, field):
    rows=[json.loads(line) for line in path.read_text().splitlines()]
    result={row[field]:row for row in rows}
    assert len(rows)==len(result)
    return result


def covered(row):
    locations={i for span in row['core']['pred'] for i in range(span['start'],span['end'])}
    return [all(i in locations for i in range(span['start'],span['end'])) for span in row['gold']]


def detector_availability(rows, name):
    """Keep partial masks, missing predictions and processing failures separate."""
    statuses=Counter();types=defaultdict(Counter);counts=Counter()
    for row in rows.values():
        status=row.get('evaluation_status','completed')
        if status!='completed':
            statuses[status]+=1
            continue
        prediction=row.get(name)
        if prediction is None:
            statuses['not_measured']+=1
            continue
        if prediction.get('enabled') is False:
            statuses['not_enabled']+=1
            continue
        if prediction.get('error_type'):
            statuses['processing_error:'+prediction['error_type']]+=1
            continue
        statuses['available']+=1
        locations={i for span in prediction['pred'] for i in range(span['start'],span['end'])}
        for span in row['gold']:
            covered_chars=sum(i in locations for i in range(span['start'],span['end']))
            types[span['label']].update(gold_entities=1,
                fully_covered=int(covered_chars==span['end']-span['start']),
                partially_covered=int(0<covered_chars<span['end']-span['start']),
                not_covered=int(covered_chars==0))
        counts.update(prediction['chars'])
        counts.update(context_chunks=prediction['context_chunks'],
                      retained_context_chunks=prediction['retained_context_chunks'])
    return {'observation_statuses':dict(statuses),
        'coverage_scope':'available predictions only; errors/unknown/not measured excluded, never counted safe',
        'by_gold_type':{label:dict(value) for label,value in types.items()},
        'character_and_context_counts':dict(counts)}


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    for name in ('previous-pii','current-pii','previous-credentials','current-credentials','output'):
        parser.add_argument('--'+name,type=Path,required=True)
    args=parser.parse_args()
    assert not args.output.exists()
    result={'independent_unseen_evaluation':False,'detector_calls':0,'pii':{},'credentials':{},
            'comparison_driver_sha256':hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
            'literal_presence_is_position_sensitive':False,'input_record_hashes':{}}
    for dataset in ('zh_formal','zh_chat','en_test'):
        filename=dataset+'-records.jsonl'
        a=records(args.previous_pii/filename,'id');b=records(args.current_pii/filename,'id')
        assert a.keys()==b.keys()
        transitions=Counter();same=Counter();same_types=defaultdict(Counter)
        type_availability=Counter();types=defaultdict(Counter);counts=Counter();native=defaultdict(Counter)
        unknown=Counter();unknown_gold=Counter();completed_rows=0
        core_transitions=Counter();core_success_types=defaultdict(Counter)
        core_success_counts=Counter();core_success_rows=0;core_excluded_gold=Counter()
        for identity,row in b.items():
            prior=a[identity]
            assert row['gold']==prior['gold']
            old_status=prior.get('evaluation_status','completed')
            new_status=row.get('evaluation_status','completed')
            if old_status!='completed' or new_status!='completed':
                unknown[old_status+'_to_'+new_status]+=1
                unknown_gold.update(span['label'] for span in row['gold'])
                old_decision=str(prior['module']['accepted']) if old_status=='completed' else old_status
                new_decision=str(row['module']['accepted']) if new_status=='completed' else new_status
                transitions[old_decision+'_to_'+new_decision]+=1
                continue
            completed_rows+=1
            assert row['chars']==prior['chars']
            counts['native_changed_records']+=int(row['native']['pred']!=prior['native']['pred'])
            before,after=covered(prior),covered(row)
            old_core=prior['core']['error_type'] or 'available'
            new_core=row['core']['error_type'] or 'available'
            core_transitions[old_core+'_to_'+new_core]+=1
            if old_core==new_core=='available':
                core_success_rows+=1
                for span,old,new in zip(row['gold'],before,after):
                    core_success_types[span['label']].update(gold_entities=1,
                        previous_fully_covered=int(old),current_fully_covered=int(new),
                        gained=int(new and not old),lost=int(old and not new))
                for prefix,record in (('previous',prior),('current',row)):
                    core_success_counts[prefix+'_masked_non_pii_chars']+=record['core']['chars']['masked_non_pii_chars']
                    core_success_counts[prefix+'_retained_context_chunks']+=record['core']['retained_context_chunks']
                core_success_counts['non_pii_chars']+=row['core']['chars']['non_pii_chars']
                core_success_counts['context_chunks']+=row['core']['context_chunks']
            else:
                core_excluded_gold.update(span['label'] for span in row['gold'])
            native_locations={i for span in row['native']['pred'] for i in range(span['start'],span['end'])}
            for span,old,new in zip(row['gold'],before,after):
                types[span['label']].update(gold_entities=1,previous_fully_covered=int(old),current_fully_covered=int(new),
                    gained=int(new and not old),lost=int(old and not new))
                native[span['label']].update(gold_entities=1,fully_covered_entities=int(all(
                    i in native_locations for i in range(span['start'],span['end']))))
            for prefix,record in (('previous',prior),('current',row)):
                counts[prefix+'_masked_non_pii_chars']+=record['core']['chars']['masked_non_pii_chars']
                counts[prefix+'_retained_context_chunks']+=record['core']['retained_context_chunks']
                counts[prefix+'_core_processing_errors']+=int(record['core']['error_type'] is not None)
            counts['non_pii_chars']+=row['core']['chars']['non_pii_chars']
            counts['context_chunks']+=row['core']['context_chunks']
            old,new=prior['module'],row['module']
            transitions[str(old['accepted'])+'_to_'+str(new['accepted'])]+=1
            if old['accepted'] and new['accepted']:
                assert old['gold_entities']==new['gold_entities']
                same.update(documents=1,gold_entities=new['gold_entities'],
                    previous_literal_residual_entities=old['literal_residual_entities'],
                    current_literal_residual_entities=new['literal_residual_entities'])
                if 'by_gold_type' in old and 'by_gold_type' in new:
                    type_availability['available_documents']+=1
                    assert old['by_gold_type'].keys()==new['by_gold_type'].keys()
                    for label,after_type in new['by_gold_type'].items():
                        before_type=old['by_gold_type'][label]
                        assert before_type['gold_entities']==after_type['gold_entities']
                        same_types[label].update(gold_entities=after_type['gold_entities'],
                            previous_literal_residual_entities=before_type['literal_residual_entities'],
                            current_literal_residual_entities=after_type['literal_residual_entities'])
                else:
                    type_availability['unavailable_documents']+=1
        result['pii'][dataset]={'rows':len(b),'completed_comparison_rows':completed_rows,
            'unknown_transitions':dict(unknown),'unknown_gold_entities_by_type':dict(unknown_gold),
            'coverage_and_character_scope':'same completed observations only; unknown never safe, rejected or fully masked',
            'admission_transitions':dict(transitions),'same_admitted_cohort':dict(same),
            'same_admitted_cohort_by_gold_type':{label:dict(value) for label,value in same_types.items()},
            'same_admitted_per_type_availability':dict(type_availability),
            'by_gold_type':{key:dict(value) for key,value in types.items()},
            'native_by_gold_type':{key:dict(value) for key,value in native.items()},'counts':dict(counts),
            'core_processing_transitions':dict(core_transitions),
            'same_successful_core_cohort':{'rows':core_success_rows,
                'excluded_processing_error_gold_by_type':dict(core_excluded_gold),
                'scope':'same completed observations with both core predictions available; not a replacement for full-denominator pressure view',
                'by_gold_type':{key:dict(value) for key,value in core_success_types.items()},
                'counts':dict(core_success_counts)},
            'current_detector_availability':{name:detector_availability(b,name)
                for name in ('native','core','official_opf')},
            'current_rejection_decision_reasons':dict(Counter(row['module'].get('decision_reason','not_recorded')
                for row in b.values() if row.get('evaluation_status','completed')=='completed' and not row['module']['accepted']))}
        result['input_record_hashes'][dataset]={name:hashlib.sha256((folder/filename).read_bytes()).hexdigest()
            for name,folder in (('previous',args.previous_pii),('current',args.current_pii))}
    filename='module-file-records-private.jsonl'
    a=records(args.previous_credentials/filename,'file');b=records(args.current_credentials/filename,'file')
    assert a.keys()==b.keys() and len(b)==11030
    transitions=Counter();same=Counter();native_risk=0
    for identity,row in b.items():
        prior=a[identity]
        assert prior['truth']==row['truth'] and prior['gitleaks_flagged']==row['gitleaks_flagged']
        transitions[prior['status']+'_to_'+row['status']]+=1
        if prior['accepted'] is True and row['accepted'] is True:
            assert prior['extractable_positive_rows']==row['extractable_positive_rows']
            same.update(files=1,extractable_positive_rows=row['extractable_positive_rows'],
                previous_literal_residual_rows=prior['literal_residual_rows'],current_literal_residual_rows=row['literal_residual_rows'])
        native_risk+=int(row['accepted'] is True and row['gitleaks_flagged'] and row.get('any_literal_residual',False))
    result['credentials']={'files':len(b),'status_transitions':dict(transitions),'same_admitted_cohort':dict(same),
        'native_flagged_accepted_files_with_literal_residual':native_risk,
        'current_rejection_decision_reasons':dict(Counter(row.get('decision_reason','not_recorded')
            for row in b.values() if row['accepted'] is False))}
    result['input_record_hashes']['credentials']={name:hashlib.sha256((folder/filename).read_bytes()).hexdigest()
        for name,folder in (('previous',args.previous_credentials),('current',args.current_credentials))}
    args.output.write_text(json.dumps(result,indent=2)+'\n')
    print(json.dumps({'pii_rows':sum(row['rows'] for row in result['pii'].values()),'credential_files':len(b)}))


if __name__=='__main__':main()
