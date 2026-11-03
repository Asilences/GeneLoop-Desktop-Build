"""Read-only host execution or explicit candidate validation using native grants."""
import json,subprocess
from pathlib import Path
from src.adapters.capability_scene import ROOT,reference
from src.adapters.capability_improvement import evidence,save
from src.adapters.capability_contract import capability_digest


def execute(snapshot,root,libraries,inputs,args,directory,task_id,*,mode='execute'):
    # Only trusted host callers select validation; candidate source cannot
    # manufacture a grant. The native runtime still certifies every dependency.
    if mode not in ('execute','validate'):raise ValueError('frontier_execution_mode_invalid')
    directory=Path(directory);(directory/'work/inputs').mkdir(parents=True,exist_ok=False,mode=0o700)
    bound=[]
    for item in inputs:
        path=item['path']
        if path!='/work/inputs/'+Path(path).name:raise ValueError('frontier_input_path_invalid')
        target=directory/'work/inputs'/Path(path).name;target.write_bytes(evidence(item['source']));target.chmod(0o400)
        bound.append({'path':path,'sha256':reference(target)['sha256']})
    for ref in libraries:evidence(ref)
    manifest={'format':'script_capability_task_v1','task_id':task_id,'owner':snapshot['owner'],
        'workspace':str((directory/'work').resolve()),'registry_path':str((directory/'snapshot.json').resolve()),
        'libraries':libraries,'inputs':bound,'grant':{'id':'frontier-'+task_id,'task_id':task_id,
        'snapshot_sha256':snapshot['digest'],'root':root,'arguments_sha256':capability_digest(args),
        'mode':mode,'effects':['read'],'revoked':False}}
    for name,value in [('snapshot',snapshot),('manifest',manifest),('args',args)]:save(directory/(name+'.json'),value)
    run=subprocess.run(['node','scripts/run-script-capability.mjs','--manifest',str(directory/'manifest.json'),
        '--snapshot',str(directory/'snapshot.json'),'--args',str(directory/'args.json')],cwd=ROOT,capture_output=True,text=True,timeout=90)
    (directory/'stderr.log').write_text(run.stderr);(directory/'trace.json').write_text(run.stdout)
    trace=json.loads(run.stdout)
    if run.returncode or trace.get('status')!='succeeded':raise ValueError('frontier_execution_failed:'+json.dumps(trace)[:8000])
    return trace
