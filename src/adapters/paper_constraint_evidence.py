"""Extract current Paper constraint witnesses from bound task tool receipts."""
import json
from pathlib import Path

from src.motif_core.offline.compilation.script_motif_compiler import digest, sha


def constraint_observations(task):
    task=Path(task).resolve();cfg=json.loads((task/'effective-config.json').read_text());work=Path(cfg['workspace']).resolve()
    if not work.is_relative_to(task.parent.parent):raise ValueError('foreign_constraint_workspace')
    path=work/'review-recovery-scope.json'
    if path.resolve()!=path or not path.is_file():return []
    raw=path.read_bytes();goal=json.loads(raw)
    if goal.get('task_id')!=task.name or goal.get('policy')!='preserve_structure_allow_semantic_leaf_revisions':return []
    grant=json.loads((work/'paper-output-grant.json').read_bytes())
    if grant.get('allow_output') is not True or grant.get('task_id')!=task.name:return []
    calls={};found=[];events=(task/'events.jsonl').read_bytes()
    events_sha256=sha(events)
    for event in map(json.loads,events.splitlines()):
        d=event.get('data',{})
        if event['type']=='tool/call':
            a=d['arguments'];calls[d['callId']]=(d['name'],json.loads(a) if isinstance(a,str) else a)
        if event['type']!='tool/result':continue
        for b in d.get('message',{}).get('content',[]):
            call=calls.pop(b.get('toolCallId'),None)
            if call is None or b.get('isError'):continue
            try:v=json.loads(next(c['text'] for c in b['content'] if c['type']=='text'))
            except (ValueError,KeyError,StopIteration):continue
            e=v.get('execution_evidence',{}) if isinstance(v,dict) else {};args=call[1]
            if e.get('arguments_sha256')!=digest(args) or e.get('recovery_scope_sha256')!=sha(raw) or e.get('task_id')!=task.name or e.get('grant_sha256')!=digest(grant) or e.get('source_versions')!=goal['source_versions'] or args.get('source_versions')!=goal['source_versions']:continue
            found.append({'tool':call[0],'arguments':args,'goal':goal['arguments'],'result':v,
                          'call_id':b['toolCallId'],'task_id':task.name,'events_sha256':events_sha256})
    return found
