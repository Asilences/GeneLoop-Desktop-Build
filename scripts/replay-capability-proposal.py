"""Replay a saved answer offline; optional wrapper-only edit is a human diagnostic.

Never calls a model, executes a capability, publishes, or modifies source files.
"""
from pathlib import Path
import argparse
import copy
import hashlib
import json
import sys
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
from src.adapters.capability_authoring import expand_draft, compact_proposal, diagnose
from src.adapters.capability_builder import compile_proposal
from src.adapters.capability_contract import capability_digest
from scenarios.remotion_edit.structured.run_capability_loop import parse_proposal


def save(path,value):
    with path.open('x') as f:json.dump(value,f,ensure_ascii=False,indent=2,allow_nan=False)
    path.chmod(0o600)


def repair_wrappers(proposal):
    """Add only missing object-binding wrappers around already typed children."""
    value=copy.deepcopy(proposal);patches=[]
    def visit(binding,path):
        if not isinstance(binding,dict):return binding
        if binding and 'kind' not in binding and all(isinstance(v,dict) and v.get('kind') in ('input','step','literal','object','array') for v in binding.values()):
            patches.append({'path':path,'operation':'wrap_object_binding','before_sha256':capability_digest(binding)})
            return {'kind':'object','fields':copy.deepcopy(binding)}
        if binding.get('kind')=='object' and isinstance(binding.get('fields'),dict):
            binding['fields']={k:visit(v,path+['fields',k]) for k,v in binding['fields'].items()}
        if binding.get('kind')=='array' and isinstance(binding.get('items'),list):
            binding['items']=[visit(v,path+['items',i]) for i,v in enumerate(binding['items'])]
        return binding
    for index,step in enumerate(value.get('steps',[])):
        if isinstance(step,dict) and 'arguments' in step:step['arguments']=visit(step['arguments'],['steps',index,'arguments'])
    if 'output' in value:value['output']=visit(value['output'],['output'])
    return value,patches


def replay(answer_path,task_path,snapshot_path,output,repair=False):
    output=Path(output);output.mkdir(parents=True,exist_ok=False,mode=0o700)
    raw=Path(answer_path).read_text();task=json.loads(Path(task_path).read_text());snapshot=json.loads(Path(snapshot_path).read_text())
    summary={'format':'capability_proposal_replay_v1','model_calls':0,'execution_calls':0,'published':False,
             'scope':'offline_diagnostic_not_agent_repair','sources':{label:hashlib.sha256(Path(p).read_bytes()).hexdigest() for label,p in [('answer',answer_path),('task',task_path),('snapshot',snapshot_path)]},
             'code_sha256':{name:hashlib.sha256((ROOT/name).read_bytes()).hexdigest() for name in ['scripts/replay-capability-proposal.py','src/adapters/capability_authoring.py','src/adapters/capability_builder.py','src/adapters/capability_contract.py','scenarios/remotion_edit/structured/run_capability_loop.py']}}
    draft=proposal=None
    try:
        draft=parse_proposal(raw);proposal=expand_draft(draft,task,snapshot)
        original=compile_proposal(proposal,snapshot,snapshot['owner'])
        summary['original']={'status':'compiled','capability_id':original['capability']['id']}
    except ValueError as error:summary['original']={'status':'failed','diagnostics':diagnose(error,proposal)}
    if repair and isinstance(draft,dict) and draft.get('format')=='capability_compose_proposal_v1':
        fixed,patches=repair_wrappers(draft)
        save(output/'wrapper-patches.json',patches)
        save(output/'diagnostic-proposal.json',fixed)
        try:
            compiled=compile_proposal(expand_draft(fixed,task,snapshot),snapshot,snapshot['owner'])
            compact=compact_proposal(fixed,task,snapshot)
            expanded=expand_draft(compact,task,snapshot)
            if expanded!=fixed:raise ValueError('proposal_roundtrip_changed')
            save(output/'compiled-candidate.json',compiled);save(output/'compact-draft.json',compact)
            summary['diagnostic_edit']={'status':'compiled','wrappers_added':len(patches),'roundtrip_exact':True,
                'capability_id':compiled['capability']['id'],'raw_proposal_bytes':len(json.dumps(fixed,ensure_ascii=False,separators=(',',':')).encode()),
                'compact_draft_bytes':len(json.dumps(compact,ensure_ascii=False,separators=(',',':')).encode())}
        except ValueError as error:summary['diagnostic_edit']={'status':'failed','diagnostics':diagnose(error,fixed),'wrappers_added':len(patches)}
    save(output/'result.json',summary)
    return summary


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    for name in ['answer','task','snapshot','output']:parser.add_argument('--'+name,type=Path,required=True)
    parser.add_argument('--repair-object-wrappers',action='store_true')
    args=parser.parse_args()
    if not args.output.resolve().is_relative_to(ROOT/'.local'):parser.error('raw replay artifacts must remain in project .local')
    result=replay(args.answer,args.task,args.snapshot,args.output,args.repair_object_wrappers)
    print(json.dumps(result,ensure_ascii=False))

if __name__=='__main__':main()
