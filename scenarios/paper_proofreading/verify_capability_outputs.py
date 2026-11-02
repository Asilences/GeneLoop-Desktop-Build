"""Independent literal BibTeX inventory check; not publication truth or full review."""
import argparse
from collections import Counter
import hashlib
import json
from pathlib import Path
import sys
ROOT=Path(__file__).resolve().parents[2];sys.path.insert(0,str(ROOT))
from src.adapters.paper_bibliography import bib_records
from src.adapters.capability_contract import capability_digest


def verify(manifest,trace,specification):
    if specification.get('kind')!='bibtex_inventory_v1':raise ValueError('paper_checker_scope_unsupported')
    fields=specification['fields']
    if set(fields)!={'entry_count','unique_key_count','duplicate_keys'}:raise ValueError('paper_checker_fields_required')
    path=specification['source_path']
    if not isinstance(path,str) or path!='/work/inputs/'+Path(path).name:raise ValueError('paper_checker_input_invalid')
    workspace=Path(manifest['workspace']).resolve(strict=True)
    source=workspace/'inputs'/Path(path).name
    if source.resolve(strict=True)!=source:raise ValueError('paper_checker_input_redirected')
    raw=source.read_bytes();sha=hashlib.sha256(raw).hexdigest()
    if {'path':path,'sha256':sha} not in manifest['inputs']:raise ValueError('paper_checker_input_changed')
    rows=bib_records(raw.decode('utf-8-sig'))
    if not rows:raise ValueError('paper_checker_no_literal_entries')
    counts=Counter(row['key'] for row in rows)
    expected={'entry_count':len(rows),'unique_key_count':len(counts),'duplicate_keys':sorted(key for key,count in counts.items() if count>1)}
    checks=[{'id':'task_and_input_binding','status':'passed' if trace.get('task_id')==manifest['task_id'] and
        trace.get('owner')==manifest['owner'] and trace.get('status')=='succeeded' and
        trace.get('input_versions')==manifest['inputs'] else 'failed',
        'observation':'核对任务、owner、执行状态和当前输入摘要'}]
    for key,parts in fields.items():
        if not isinstance(parts,list) or any(not isinstance(p,str) or p in ('__proto__','constructor','prototype') for p in parts):
            raise ValueError('paper_checker_result_path_invalid')
        actual=trace.get('result')
        try:
            for part in parts:actual=actual[part]
        except (KeyError,TypeError):actual=None
        # Booleans are not counts; duplicate keys must be a unique sorted list.
        ok=type(actual) is type(expected[key]) and actual==expected[key]
        checks.append({'id':key,'status':'passed' if ok else 'failed',
            'observation':json.dumps({'expected':expected[key],'actual':actual},ensure_ascii=False)})
    return {'passed':all(c['status']=='passed' for c in checks),'checks':checks,
        'scope':'literal_bibtex_entry_and_key_inventory',
        'limitations':['不核验文献真实性、字段质量或完整论文报告；仅支持现有解析器的字面花括号语法'],
        'evidence_binding':{'input_sha256':sha,'trace_sha256':capability_digest(trace)}}


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    for name in ('manifest','trace','specification'):parser.add_argument('--'+name,type=Path,required=True)
    args=parser.parse_args()
    print(json.dumps(verify(*[json.loads(getattr(args,name).read_text(encoding='utf-8')) for name in ('manifest','trace','specification')]),ensure_ascii=False))
