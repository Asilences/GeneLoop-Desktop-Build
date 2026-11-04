"""Run the RAE mechanism acceptance; retain real execution evidence privately.

Deterministic tasks, actual Runtime/miner/compiler/Store operations, zero model
requests. This command never enables production or asserts autonomous benefits.
"""
import argparse
import hashlib
import json
import os
from pathlib import Path
import subprocess
import sys
from datetime import datetime, timezone

ROOT = Path(__file__).resolve().parents[1]


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', type=Path)
    args = parser.parse_args()
    output = (args.output or ROOT/'.local'/('rae-check-'+datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%S%fZ'))).resolve()
    if not output.is_relative_to((ROOT/'.local').resolve()):
        parser.error('raw evidence must remain in private .local')
    output.mkdir(parents=True, exist_ok=False, mode=0o700)
    python_tests = ['tests/test_capability_'+name+'.py' for name in (
        'motif_learning', 'evolution', 'evolution_runtime', 'builder_application',
        'abstraction_view', 'learned_candidate', 'composition_projection')]
    python_tests.extend(['tests/test_recursive_learning_cli.py', 'tests/test_recursive_paper_candidate.py',
                         'tests/test_rae_real_acceptance.py', 'tests/test_builder_program_learning.py'])
    # No fixed/mock provider substitutes: these tests invoke actual local native
    # operations with diagnostic seed authority, separately labelled in reports.
    commands = [
        [sys.executable, '-m', 'pytest', '-q', *python_tests,
         '--basetemp='+str(output/'traces'), '--junitxml='+str(output/'python.xml')],
        ['node', '--test', 'tests/test_capability_discharge.mjs'],
    ]
    files = [*python_tests, 'tests/test_capability_discharge.mjs',
             'src/adapters/capability_motif_learning.py', 'src/adapters/capability_discharge.ts',
             'src/adapters/capability_evolution.py', 'src/adapters/capability_builder_application.py']
    def git_value(*arguments):
        result = subprocess.run(['git', *arguments], cwd=ROOT, text=True, capture_output=True)
        return result.stdout.strip() if result.returncode == 0 else None
    top = git_value('rev-parse', '--show-toplevel')
    own_checkout = top is not None and Path(top).resolve() == ROOT.resolve()
    effective = {'format':'rae_mechanism_acceptance_v1', 'evidence_level':'wiring_pending',
        'model_requests':0, 'model_cost_usd':'0', 'total_cost':None,
        'autonomous_constructed':False, 'measured_improvement':None,
        'python':sys.version, 'node':subprocess.check_output(['node','--version'],text=True).strip(),
        'head':git_value('rev-parse','HEAD') if own_checkout else None,
        'status':git_value('status','--porcelain') if own_checkout else None,
        'source_identity':'git_checkout' if own_checkout else 'file_hashes_only',
        'files':{p:hashlib.sha256((ROOT/p).read_bytes()).hexdigest() for p in files},
        'commands':commands, 'outcomes':[]}
    (output/'effective.json').write_text(json.dumps(effective,indent=2),encoding='utf-8')
    for index, command in enumerate(commands):
        with (output/('check-'+str(index)+'.log')).open('w',encoding='utf-8') as log:
            result = subprocess.run(command,cwd=ROOT,stdout=log,stderr=subprocess.STDOUT,
                                    env={**os.environ,'SSS_PYTHON':sys.executable})
        effective['outcomes'].append({'command':index,'exit_code':result.returncode})
        print((output/('check-'+str(index)+'.log')).read_text(encoding='utf-8'),flush=True)
    effective['status']='passed' if all(row['exit_code']==0 for row in effective['outcomes']) else 'failed'
    effective['evidence_level']='wiring_passed' if effective['status']=='passed' else 'wiring_failed'
    (output/'result.json').write_text(json.dumps(effective,indent=2),encoding='utf-8')
    print(json.dumps({'status':effective['status'],'evidence_directory':str(output)}))
    return 0 if effective['status']=='passed' else 1


if __name__=='__main__':
    raise SystemExit(main())
