"""Stable Task evidence with live semantic revalidation, separate from UI progress."""
from __future__ import annotations
import hashlib
import json
from src.adapters.filesystem_paths import Path
import re

STATE_KEYS=('task_id','session_id','user_id','scene','mode','status','failure','source_task_id',
            'provider_mode','provider','model','reasoning_effort','scene_inputs','rsi','scene_options')
STATS_KEYS=('upstream_requests','prompt_tokens','prompt_cache_hit_tokens','prompt_cache_miss_tokens',
            'completion_tokens','total_tokens','usage_complete','pending_requests','unknown_usage_requests','verified_skips')
PATTERN=re.compile(r'learning-state-([a-f0-9]{64})\.json')
STRUCTURE_PATTERN=re.compile(r'learning-structure-([a-f0-9]{64})\.json')

def projection(state, *, structure_only=False):
    keys=('verified_skips',) if structure_only else STATS_KEYS
    return {**{k:state.get(k) for k in STATE_KEYS},'stats':{k:state.get('stats',{}).get(k) for k in keys}}

def digest(value):
    return hashlib.sha256(json.dumps(value,ensure_ascii=False,sort_keys=True,separators=(',',':'),allow_nan=False).encode()).hexdigest()

def freeze_state(output,directory,state,*,structure_only=False):
    """A new immutable projection never changes an older certificate's bytes."""
    output=Path(output);directory=Path(directory)
    identity=state.get('task_id')
    if not isinstance(identity,str) or not re.fullmatch('[a-f0-9]{32}',identity) or directory!=output/'tasks'/identity:
        raise ValueError('invalid learning state owner')
    value=projection(state,structure_only=structure_only);version=digest(value)
    path=directory/(('learning-structure-' if structure_only else 'learning-state-')+version+'.json')
    record={'schema_version':2 if structure_only else 1,'kind':'ppt_learning_state_binding_v2' if structure_only else 'ppt_learning_state_binding_v1',
            'task_id':identity,'state_sha256':version,'state':value}
    if structure_only:record['scope']='structural_facts_excluding_billing'
    raw=json.dumps(record,ensure_ascii=False,sort_keys=True,separators=(',',':'),allow_nan=False).encode()
    if path.exists():
        if path.is_symlink() or path.stat().st_nlink!=1 or path.read_bytes()!=raw:raise ValueError('learning state binding changed')
    else:
        with path.open('xb') as stream:stream.write(raw)
        path.chmod(0o600)
    return path

def verify_state_binding(output,path):
    output=Path(output);path=Path(path)
    structure_only=STRUCTURE_PATTERN.fullmatch(path.name) is not None
    match=(STRUCTURE_PATTERN if structure_only else PATTERN).fullmatch(path.name)
    if not match:return
    row=json.loads(path.read_text(encoding='utf-8'));identity=row.get('task_id')
    if (not isinstance(identity,str) or not re.fullmatch('[a-f0-9]{32}',identity) or path.parent!=output/'tasks'/identity or
        row.get('schema_version')!=(2 if structure_only else 1) or row.get('kind')!=('ppt_learning_state_binding_v2' if structure_only else 'ppt_learning_state_binding_v1') or
        (structure_only and row.get('scope')!='structural_facts_excluding_billing') or row.get('state_sha256')!=match[1] or digest(row.get('state'))!=match[1]):
        raise ValueError('invalid learning state binding')
    current=output/'tasks'/identity/'task-state.json'
    if current.is_symlink() or current.resolve(strict=True)!=current.absolute() or current.stat().st_nlink!=1:
        raise ValueError('learning state path changed')
    if digest(projection(json.loads(current.read_text(encoding='utf-8')),structure_only=structure_only))!=match[1]:
        raise ValueError('learning task facts changed')
