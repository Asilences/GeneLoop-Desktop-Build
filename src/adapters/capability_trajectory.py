"""Read-only execution evidence projection, with unknowns kept explicit.

No dependency is inferred from equal text or temporal adjacency. Raw events and
native snapshots stay authoritative; this view neither certifies nor replays.
"""
import hashlib
import json
from pathlib import Path
from src.adapters.capability_contract import capability_digest
from src.adapters.capability_improvement import read, save


def reference(path):
    return {'path':str(path), 'sha256':hashlib.sha256(Path(path).read_bytes()).hexdigest()}


def project_web_task(task, owner):
    task=Path(task).resolve()
    state,effective,request=[read(task/name) for name in ('task-state.json','effective-config.json','task.json')]
    if state.get('user_id')!=owner or effective.get('user_id')!=owner:
        raise ValueError('trajectory_owner_changed')
    if any(row.get('task_id')!=task.name for row in (state,effective,request)):
        raise ValueError('trajectory_task_changed')
    if effective.get('provider_mode')!='real' or state.get('status') not in ('completed','failed','cancelled','interrupted'):
        raise ValueError('trajectory_real_terminal_task_required')
    refs=[reference(task/name) for name in ('task-state.json','effective-config.json','task.json','events.jsonl')]
    boundary_path=task/'reuse-boundaries.jsonl'
    boundaries={}
    if boundary_path.exists():
        refs.append(reference(boundary_path))
        for row in map(json.loads,boundary_path.read_text().splitlines()):
            if row['call_id'] in boundaries:raise ValueError('trajectory_duplicate_boundary')
            boundaries[row['call_id']]=row
    events=[json.loads(line) for line in (task/'events.jsonl').read_text().splitlines() if line]
    calls={};steps=[]
    start=effective.get('trace_start_index',0)
    if type(start) is not int or not 0<=start<=len(events):raise ValueError('trajectory_trace_boundary_invalid')
    for index,event in enumerate(events[start:],start):
        data=event.get('data',{})
        if event.get('type')=='tool/call':
            identity=data['callId']
            if identity in calls:raise ValueError('trajectory_duplicate_call')
            args=data['arguments'];args=json.loads(args) if isinstance(args,str) else args
            boundary=boundaries.get(identity)
            if boundary:
                # Native boundary hashes use the legacy serialization, not the
                # cross-language Capability digest.
                from src.adapters.script_motif_compiler import digest
                if boundary['arguments_sha256']!=digest(args):raise ValueError('trajectory_arguments_changed')
            step={'call_id':identity,'tool':data['name'],'arguments':args,'call_event_index':index,
                  'result_event_index':None,'status':'unresolved','result':None,
                  'parameter_sources':None,'preconditions':None,
                  'boundary':boundary,'dependencies':None}
            calls[identity]=step;steps.append(step)
        elif event.get('type')=='tool/result':
            for block in data.get('message',{}).get('content',[]):
                if block.get('type')!='tool-result':continue
                step=calls.get(block.get('toolCallId'))
                if step is None:continue
                if step['result_event_index'] is not None:raise ValueError('trajectory_duplicate_result')
                step.update(result_event_index=index,result=block,
                    status='failed' if block.get('isError') else 'succeeded')
    accounting=task/'learning-accounting.json'
    if accounting.exists():refs.append(reference(accounting))
    return {'format':'capability_trajectory_v1','owner':owner,'task_id':task.name,
            'scene':state.get('scene'),'mode':effective.get('mode'),'status':state['status'],
            'source_task_id':state.get('source_task_id',task.name),
            'evidence':refs,'steps':steps,'tools':effective.get('tools'),
            'accounting':reference(accounting) if accounting.exists() else None,
            'quality':'unreviewed','split':'unassigned','benefit':None,
            'scope':'observed_calls_and_native_boundaries_not_inferred_dataflow_or_quality'}


def record_web_task(task,owner,directory):
    value=project_web_task(task,owner)
    directory=Path(directory);directory.mkdir(parents=True,exist_ok=True,mode=0o700)
    path=directory/(capability_digest(value)+'.json')
    if not path.exists():save(path,value)
    elif read(path)!=value:raise ValueError('trajectory_record_changed')
    return reference(path)
