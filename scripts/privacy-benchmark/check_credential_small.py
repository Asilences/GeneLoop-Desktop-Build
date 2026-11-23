"""Paired credential pilot gate. Unknown is never treated as rejection/safe."""
import argparse,json
from pathlib import Path


def main():
    parser=argparse.ArgumentParser()
    for name in ['baseline','candidate','output']:parser.add_argument('--'+name,type=Path,required=True)
    args=parser.parse_args()
    def read(root):
        rows=[json.loads(line) for line in (root/'rows-private.jsonl').read_text().splitlines()]
        result={r['file']:r for r in rows};assert len(rows)==len(result)
        return result
    before,after=read(args.baseline),read(args.candidate)
    assert before.keys()==after.keys() and len(before)==18
    failures=[];counts={'records':len(before),'new_unknown':0,'new_rejection':0,'rejection_lost':0,'residual_increase':0}
    for key,a in before.items():
        b=after[key];assert a['truth']==b['truth'] and a['input_sha256']==b['input_sha256']
        if a['status']=='completed' and b['status']!='completed':counts['new_unknown']+=1
        if a['accepted'] is True and b['accepted'] is False:counts['new_rejection']+=1
        if a['accepted'] is False and b['accepted'] is True:counts['rejection_lost']+=1
        if a['accepted'] is True and b['accepted'] is True and b['literal_residual_rows']>a['literal_residual_rows']:
            counts['residual_increase']+=1
    failures=[key for key in ['new_unknown','new_rejection','rejection_lost','residual_increase'] if counts[key]]
    result={'passed':not failures,'failed':failures,**counts,'scope':'non-regression pilot; not proof of zero credential leaks'}
    args.output.write_text(json.dumps(result,indent=2)+'\n');print(json.dumps(result))
    raise SystemExit(0 if result['passed'] else 1)


if __name__=='__main__':main()
