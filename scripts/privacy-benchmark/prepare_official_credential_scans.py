"""Fresh native Gitleaks/CredSweeper scans; public output is aggregate only."""
import argparse
from collections import Counter,defaultdict
import hashlib
import json
import os
from pathlib import Path
import subprocess
import sys
import time

import run_credentials as legacy


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    for name in ('repo','root','scoring','output'):
        parser.add_argument('--'+name,type=Path,required=True)
    args=parser.parse_args()
    assert not args.output.exists()
    args.output.mkdir(mode=0o700,parents=True)
    sys.path.insert(0,str(args.repo.resolve()));sys.path.insert(0,str(args.root.resolve()))
    from src.adapters.rsi_privacy_tools import verified_gitleaks
    from src.adapters.rsi_privacy_candidates import _verify_distribution,_MANIFEST
    manifest=json.loads(_MANIFEST.read_text())
    _verify_distribution('credsweeper',manifest['credsweeper'])
    annotations=legacy.read_annotations(args.scoring)
    groups=defaultdict(list)
    for row in annotations:groups[row['FilePath']].append(row)
    assert len(groups)==11030 and len(annotations)==67896
    input_hashes={name:hashlib.sha256((args.scoring/name).read_bytes()).hexdigest() for name in sorted(groups)}
    snapshot={'data_digest':hashlib.sha256(json.dumps(input_hashes,sort_keys=True).encode()).hexdigest(),
              'files':len(groups),'annotation_rows':len(annotations),
              'labels':dict(Counter(row['GroundTruth'] for row in annotations)),
              'sources':len(list((args.scoring/'meta').glob('*.csv'))),
              'driver_sha256':hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
              'candidate_manifest_sha256':hashlib.sha256(_MANIFEST.read_bytes()).hexdigest(),
              'cloud_requests':0,'native_scans_newly_executed':True}
    (args.output/'credential-frozen-snapshot.json').write_text(json.dumps(snapshot,indent=2))
    data=(args.scoring/'data').resolve()
    binary=verified_gitleaks(os.environ['SSS_RSI_GITLEAKS'])
    tools={
        'gitleaks':[str(binary),'dir',str(data),'--no-banner','--redact=100','--ignore-gitleaks-allow','--max-decode-depth','2',
                    '--report-format','json','--report-path',str((args.output/'gitleaks-modern-private.json').resolve())],
        'credsweeper':[sys.executable,'-c','import onnxruntime as o,runpy; o.disable_telemetry_events(); runpy.run_module("credsweeper",run_name="__main__")','--path',str(data),'--jobs','16',
                       '--ml_threshold','medium','--ml_threads_limit','1','--ml_providers','CPUExecutionProvider',
                       '--no-stdout','--hashed','--log','CRITICAL','--save-json',str((args.output/'credsweeper-native-private.json').resolve())]}
    times={}
    for name,command in tools.items():
        start=time.perf_counter()
        with (args.output/(name+'-private.log')).open('w') as log:
            completed=subprocess.run(command,cwd=args.output,stdout=log,stderr=log,check=False)
        assert completed.returncode in ((0,1) if name=='gitleaks' else (0,)), name+'_native_scan_failed'
        times[name]={'seconds':time.perf_counter()-start,'exit_code':completed.returncode}
        print(json.dumps({'native_scan':name,'finished':True,**times[name]}),flush=True)
    gitleaks=json.loads((args.output/'gitleaks-modern-private.json').read_text())
    sweeper=json.loads((args.output/'credsweeper-native-private.json').read_text())
    def relative(path):
        path=Path(path)
        if not path.is_absolute():path=(args.output/path).resolve()
        return 'data/'+path.resolve().relative_to(data).as_posix()
    leaks={relative(row['File']) for row in gitleaks}
    swept={relative(line['path']) for row in sweeper for line in row['line_data_list']}
    scores={}
    for name,flagged in [('gitleaks',leaks),('credsweeper',swept),('union',leaks|swept)]:
        scores[name]={'files':legacy.matrix([{'truth':legacy.truth_status(rows),'flagged':path in flagged} for path,rows in groups.items()]),
                      'flagged_annotated_files':len(flagged&groups.keys()),'flagged_outside_annotation_scope':len(flagged-groups.keys())}
    result={**snapshot,'times':times,'findings':{'gitleaks':len(gitleaks),'credsweeper':len(sweeper)},'scores':scores,
            'native_credsweeper':'official CLI/default filters and medium ML; original file paths; hashed values; not the memory-text module adapter',
            'training_overlap':'upstream CredSweeper training uses CredData; not unseen evaluation'}
    (args.output/'native-credential-summary.json').write_text(json.dumps(result,indent=2))
    print(json.dumps({'finished':True,'scores':{name:value['flagged_annotated_files'] for name,value in scores.items()}}),flush=True)


if __name__=='__main__':main()
