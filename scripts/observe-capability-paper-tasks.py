#!/usr/bin/env python3
"""Opt-in read-only projection of an existing owner-scoped Paper task index.

Uses the existing learning request format; never changes the certified Paper
worker, its library, original tasks, partition, accounting or execution policy.
"""
import argparse
import hashlib
import json
from pathlib import Path
import re
import sys
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT))
from src.adapters.capability_trajectory import record_web_task
from src.adapters.capability_improvement import read
from src.adapters.file_lock import exclusive_lock


def observe(request_path):
    request_path=Path(request_path).absolute();request=read(request_path)
    output=Path(request['output']).resolve(strict=True);store=request_path.parent
    owner=request['user'];scope=request['scope']
    if not isinstance(owner,str) or not isinstance(scope,str) or not re.fullmatch('[a-f0-9]{64}',scope):raise ValueError('paper_observer_identity_invalid')
    expected=output/'learning'/hashlib.sha256((owner+'\0'+scope).encode()).hexdigest()
    if request.get('schema_version')!=1 or store!=expected or store.resolve()!=store or request_path.is_symlink():
        raise ValueError('paper_observer_owner_path_invalid')
    if not output.is_relative_to((ROOT/'.local').resolve()):raise ValueError('paper_observer_private_output_required')
    records=[];rejected=[]
    with exclusive_lock(store/'capability-observer.lock'):
        for identity in dict.fromkeys(request['task_ids']):
            if not isinstance(identity,str) or not re.fullmatch('[a-f0-9]{32}',identity):raise ValueError('paper_observer_task_id_invalid')
            task=output/'tasks'/identity
            try:
                for name in ('task-state.json','effective-config.json','task.json','events.jsonl','reuse-boundaries.jsonl','learning-accounting.json'):
                    path=task/name
                    if path.exists() and (path.resolve()!=path or path.is_symlink() or not path.is_file()):raise ValueError('paper_observer_task_path_changed')
                state=read(task/'task-state.json')
                if state.get('scene')!='paper-proofreading':continue
                records.append(record_web_task(task,owner,store/'capability-trajectories'))
            except (ValueError,KeyError,OSError,TypeError) as error:
                rejected.append({'task_id':identity,'reason':str(error)[:160]})
    return {'format':'paper_capability_observation_v1','records':records,'rejected':rejected,
            'model_requests':0,'quality_cost_promoted':False}


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__);parser.add_argument('--request',type=Path,required=True)
    print(json.dumps(observe(parser.parse_args().request),ensure_ascii=False))
