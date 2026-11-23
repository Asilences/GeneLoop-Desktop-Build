"""Stratified fixed CredData pilot; labels are used only after detection."""
import argparse
from collections import defaultdict
from concurrent.futures import TimeoutError
import hashlib,json,os
from pathlib import Path
import sys
from pebble import ProcessPool
import run_pii as bench
import run_credentials as legacy


def initialize(protocol):
    bench.initialize(protocol)
    from src.adapters.rsi_privacy_candidates import candidate_context
    with candidate_context(from_environment=True):pass


def evaluate(text):
    return bench.module_result(text)


def main():
    parser=argparse.ArgumentParser()
    for name in ['root','config','output']:parser.add_argument('--'+name,type=Path,required=True)
    parser.add_argument('--per-class',type=int,default=6)
    args=parser.parse_args();assert not args.output.exists();args.output.mkdir(mode=0o700)
    sys.path.insert(0,str(args.root.parent/'CredData'))
    groups=defaultdict(list)
    for row in legacy.read_annotations(args.root):groups[row['FilePath']].append(row)
    selected=[]
    for truth in ['positive','negative','uncertain']:
        names=[name for name,rows in groups.items() if legacy.truth_status(rows)==truth]
        names.sort(key=lambda name:hashlib.sha256(('chinese-r8:'+name).encode()).digest())
        selected.extend(names[:args.per_class])
    rows=[]
    with ProcessPool(max_workers=2,initializer=initialize,initargs=(str(args.config),)) as pool:
        pending=[]
        for name in selected:
            text=(args.root/name).read_text(encoding='utf-8')
            pending.append((name,text,pool.schedule(evaluate,args=(text,),timeout=120)))
        for name,text,future in pending:
            row={'file':name,'truth':legacy.truth_status(groups[name]),'chars':len(text),
                 'input_sha256':hashlib.sha256(text.encode()).hexdigest()}
            try:
                result=future.result();row.update(result);output=row.pop('text',None)
                if row['accepted']:
                    values,unsupported=legacy.extract_positive_values(text,groups[name])
                    row.update(literal_residual_rows=sum(value in output for value in values),
                               extractable_positive_rows=len(values),unextractable_rows=unsupported)
                row['status']='completed'
            except TimeoutError:row.update(status='evaluation_timeout',accepted=None)
            except Exception as error:row.update(status='evaluation_error',accepted=None,error_type=type(error).__name__)
            rows.append(row)
            with (args.output/'rows-private.jsonl').open('a') as stream:stream.write(json.dumps(row)+'\n')
    summary={'records':len(rows),'completed':sum(r['status']=='completed' for r in rows),
             'unknown':sum(r['accepted'] is None for r in rows),
             'selection':'sha256(chinese-r8:file) per positive/negative/uncertain, full original text',
             'cloud_requests':0}
    (args.output/'summary.json').write_text(json.dumps(summary,indent=2)+'\n');print(json.dumps(summary))


if __name__=='__main__':main()
