"""Trusted offline selection; optional dispatch uses the existing TS Source Runtime.

Plan explicitly admits semantically interchangeable roots. Schema similarity
alone is never used to authorize substitution. No model requests.
"""
import argparse,json,os,subprocess,sys,signal
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT))
from src.adapters.capability_feedback import CapabilityFeedback, file_ref
from src.adapters.capability_contract import capability_digest
from src.adapters.capability_improvement import save
from src.adapters.capability_scene import run_child


def select(plan):
    seed=json.loads(Path(plan['seed']).read_text());owner=plan['owner']
    if seed['owner']!=owner:raise ValueError('selection_owner_changed')
    raw=subprocess.run(['node','--experimental-strip-types','scripts/export-capability-construction-library.mjs',plan['store'],plan['seed']],cwd=ROOT,capture_output=True,text=True,check=True)
    library=json.loads(raw.stdout)
    feedback=CapabilityFeedback(plan['feedback_directory'],owner)
    root,projected=feedback.select_execution(library,plan['eligible'],plan['scope'])
    manifest=json.loads(Path(plan['manifest']).read_text());args=json.loads(Path(plan['args']).read_text())
    if manifest['owner']!=owner:raise ValueError('selection_owner_changed')
    if manifest['grant'].get('revoked') is not False:raise ValueError('selection_grant_revoked')
    output=Path(plan['output']).resolve()
    if not output.is_relative_to(ROOT/'.local'):raise ValueError('selection_private_output_required')
    output.mkdir(parents=True,exist_ok=False,mode=0o700)
    snapshot=projected['snapshot']
    manifest['grant'].update(task_id=manifest['task_id'],mode='execute',root=root,
        snapshot_sha256=snapshot['digest'],arguments_sha256=capability_digest(args))
    manifest['registry_path']=str(output/'snapshot.json')
    for name,value in [('manifest',manifest),('snapshot',snapshot),('args',args),('root',root)]:save(output/(name+'.json'),value)
    if plan.get('specification'):
        save(output/'specification.json',json.loads(Path(plan['specification']).read_text()))
    result={'format':'capability_execution_selection_v1','root':root,'feedback_sha256':projected['feedback_sha256'],
            'scope':plan['scope'],'eligible':plan['eligible'],'quality':'not_evaluated','model_calls':0}
    save(output/'selection.json',result)
    return output,result


def execute(plan,output,result):
    if not (output/'specification.json').exists():raise ValueError('selection_independent_specification_required')
    env={**os.environ,'SSS_PYTHON':sys.executable}
    with (output/'trace.json').open('w') as out,(output/'stderr.log').open('w') as err:
        code=run_child(['node','--experimental-strip-types','scripts/run-source-capability.mjs',
            '--manifest',str(output/'manifest.json'),'--snapshot',str(output/'snapshot.json'),
            '--args',str(output/'args.json'),'--root',str(output/'root.json')],cwd=ROOT,env=env,stdout=out,stderr=err)
    result['runtime_exit_code']=code
    refs=[file_ref(output/name) for name in ('selection.json','trace.json','manifest.json','args.json','specification.json')]
    trace=json.loads((output/'trace.json').read_text())
    passed=False
    if code==0 and trace.get('status')=='succeeded':
        # Fixed host checker; a plan cannot supply arbitrary validator code.
        with (output/'validation.json').open('w') as out,(output/'validation-stderr.log').open('w') as err:
            code=run_child([sys.executable,str(ROOT/'scenarios/remotion_edit/structured/verify_capability_outputs.py'),
                '--manifest',str(output/'manifest.json'),'--trace',str(output/'trace.json'),
                '--specification',str(output/'specification.json'),'--output',str(output/'qa')],cwd=ROOT,env=env,stdout=out,stderr=err)
        refs.append(file_ref(output/'validation.json'))
        if code==0:
            qa=json.loads((output/'validation.json').read_text())
            passed=qa.get('passed') is True and bool(qa.get('checks')) and all(c.get('status')=='passed' for c in qa['checks'])
    result['quality']='passed_mechanical_checks' if passed else 'not_passed'
    feedback=CapabilityFeedback(plan['feedback_directory'],plan['owner'])
    feedback.observe(stage='execution',subject=result['root'],scope=plan['scope'],status='passed' if passed else 'failed',evidence=refs)
    if any(r.get('reason') in ('capability_legacy_changed','capability_revision_changed',
        'capability_component_version_changed','source_capability_leaf_changed') for r in trace.get('receipts',[])):
        feedback.withdraw(result['root'],'runtime_version_guard_failed',file_ref(output/'trace.json'))
    save(output/'result.json',result)
    return 0 if passed else code or 2


def main():
    def interrupted(signum,frame):raise KeyboardInterrupt('selection_interrupted')
    signal.signal(signal.SIGTERM,interrupted)
    parser=argparse.ArgumentParser(description=__doc__);parser.add_argument('--plan',type=Path,required=True);parser.add_argument('--execute',action='store_true')
    args=parser.parse_args();plan=json.loads(args.plan.read_text())
    if args.execute and not plan.get('specification'):parser.error('--execute requires an independent specification in the host plan')
    output,result=select(plan)
    if args.execute:
        returncode=execute(plan,output,result)
        print(json.dumps(result));raise SystemExit(returncode)
    print(json.dumps(result))

if __name__=='__main__':main()
