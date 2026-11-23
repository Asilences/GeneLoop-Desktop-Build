"""Attribute effective mask positions without rerunning or retuning detectors.

Native OPF includes all eight labels and has already been rendered through the
frozen observer. This is overlap of effective operations, not raw-logit causality.
"""
import argparse
from collections import Counter,defaultdict
import hashlib
import json
from pathlib import Path

def locations(spans):
    return {i for span in spans for i in range(span['start'],span['end'])}

def main():
    parser=argparse.ArgumentParser(description=__doc__)
    for name in ('previous-pii','current-pii','output'):
        parser.add_argument('--'+name,type=Path,required=True)
    args=parser.parse_args();assert not args.output.exists()
    report={'scope':'same available effective predictions; native OPF includes all eight labels',
        'causal_limit':'operation overlap cannot distinguish raw model span boundaries from upstream rendering or label conflict resolution',
        'datasets':{},'detector_calls':0,'primary_results_modified':False,
        'driver_sha256':hashlib.sha256(Path(__file__).read_bytes()).hexdigest()}
    for dataset in ('zh_formal','zh_chat','en_test'):
        sources={};hashes={}
        for mode,folder in [('previous',args.previous_pii),('current',args.current_pii)]:
            path=folder/(dataset+'-records.jsonl')
            rows=[json.loads(line) for line in path.read_text().splitlines()]
            sources[mode]={row['id']:row for row in rows}
            assert len(rows)==len(sources[mode])
            hashes[mode]=hashlib.sha256(path.read_bytes()).hexdigest()
        assert sources['previous'].keys()==sources['current'].keys()
        counts=Counter();types=defaultdict(Counter);labels=Counter();excluded=Counter()
        for identity,current in sources['current'].items():
            previous=sources['previous'][identity];assert previous['gold']==current['gold']
            old_status=previous.get('evaluation_status','completed')
            new_status=current.get('evaluation_status','completed')
            if old_status!='completed' or new_status!='completed':
                excluded[old_status+'_to_'+new_status]+=1;continue
            if previous['core']['error_type'] or current['core']['error_type'] or current['official_opf']['error_type']:
                excluded['prediction_unavailable']+=1;continue
            counts['available_pairs']+=1
            old=locations(previous['core']['pred']);new=locations(current['core']['pred'])
            native=locations(current['official_opf']['pred']);gold=locations(current['gold'])
            added=(new-old)-gold
            counts.update(added_non_gold_chars=len(added),
                added_within_native_effective_mask=len(added&native),
                added_outside_native_effective_mask=len(added-native),
                previous_mask_chars_lost=len(old-new),
                previous_gold_mask_chars_lost=len((old-new)&gold),
                previous_non_gold_mask_chars_lost=len((old-new)-gold))
            for span in current['official_opf']['pred']:
                labels[span['label']]+=len(added&set(range(span['start'],span['end'])))
            for span in current['gold']:
                indices=set(range(span['start'],span['end']));a=indices<=old;b=indices<=new;c=indices<=native
                types[span['label']].update(gold_entities=1,previous_fully_covered=int(a),
                    current_fully_covered=int(b),native_eight_label_fully_covered=int(c),
                    native_full_but_current_incomplete=int(c and not b),
                    previously_covered_gold_chars_lost=len(indices&(old-new)),
                    combined_full_without_either_individually_full=int(b and not a and not c))
        assert counts['added_non_gold_chars']==counts['added_within_native_effective_mask']+counts['added_outside_native_effective_mask']
        report['datasets'][dataset]={'counts':dict(counts),'excluded':dict(excluded),
            'added_non_gold_overlap_by_native_effective_label':dict(labels),
            'by_gold_type':{key:dict(value) for key,value in types.items()},'input_records_sha256':hashes}
    args.output.write_text(json.dumps(report,indent=2)+'\n')
    print(json.dumps({'datasets':{key:value['counts'] for key,value in report['datasets'].items()},'detector_calls':0}))

if __name__=='__main__':main()
