"""Frozen pilot adoption gate; refuses full runs on missing/failed evidence."""
import argparse
import json
from pathlib import Path


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--baseline', type=Path, required=True)
    parser.add_argument('--scalar', type=Path, required=True)
    parser.add_argument('--batch', type=Path, required=True)
    parser.add_argument('--semantics', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    def rows(directory):
        return {(r['dataset'],r['id']):r for r in map(json.loads,(directory/'rows-private.jsonl').read_text().splitlines())}
    before, scalar, after = rows(args.baseline), rows(args.scalar), rows(args.batch)
    assert before.keys()==scalar.keys()==after.keys() and before
    failed = []
    summaries = [json.loads((path/'summary.json').read_text()) for path in (args.scalar,args.batch)]
    packets = [summary['multi_field_packet'] for summary in summaries]
    if not all(packet['accepted'] for packet in packets) or packets[0].get('sha256')!=packets[1].get('sha256'):
        failed.append('multi_field_batch_scalar_mismatch_or_rejection')
    if any(scalar[k]['module'].get('output_sha256')!=after[k]['module'].get('output_sha256') or
           scalar[k]['module']['accepted']!=after[k]['module']['accepted'] for k in before):
        failed.append('batch_scalar_output_mismatch')
    totals = {}
    declared = set(json.loads((Path(__file__).resolve().parents[2]/'config/geneloop-privacy-policy-v1.json').read_text())['text']['declared_categories'])
    for dataset in sorted({k[0] for k in before}):
        keys = [k for k in before if k[0]==dataset]
        lost = extra = denominator = old_chunks = new_chunks = chunks = 0
        for k in keys:
            a,b=before[k],after[k]
            assert a['gold']==b['gold']
            if b['core']['error_type'] or a['module']['accepted'] and not b['module']['accepted']:
                failed.append(dataset+':error_or_new_rejection')
            old={i for s in a['core']['pred'] for i in range(s['start'],s['end'])}
            new={i for s in b['core']['pred'] for i in range(s['start'],s['end'])}
            lost+=sum(set(range(s['start'],s['end']))<=old and not set(range(s['start'],s['end']))<=new for s in a['gold'] if s['label'] in declared)
            extra+=b['core']['chars']['masked_non_pii_chars']-a['core']['chars']['masked_non_pii_chars']
            denominator+=a['core']['chars']['non_pii_chars']
            chunks+=a['core']['context_chunks']
            old_chunks+=a['core']['retained_context_chunks'];new_chunks+=b['core']['retained_context_chunks']
        totals[dataset]={'lost_existing_coverage':lost,'extra_gold_complement_masking':extra/max(1,denominator),
                         'context_retention_drop':(old_chunks-new_chunks)/max(1,chunks)}
        if lost or extra/max(1,denominator)>.001 or (old_chunks-new_chunks)/max(1,chunks)>.005:
            failed.append(dataset+':quality_gate')
    semantic=json.loads(args.semantics.read_text())
    if semantic['accepted']!=24 or semantic['retained_invariants']!=120 or semantic['literal_residual_values']:
        failed.append('semantic_gate')
    if not all(semantic['secret_field_controls_rejected']):failed.append('credential_controls')
    result={'passed':not failed,'failed':sorted(set(failed)),'datasets':totals,
            'multi_field_seconds':{'scalar':packets[0]['seconds'],'batch':packets[1]['seconds']},
            'scope':'development pilot only; not production privacy certification'}
    args.output.write_text(json.dumps(result,indent=2)+'\n');print(json.dumps(result))
    raise SystemExit(0 if result['passed'] else 1)


if __name__=='__main__':main()
