"""Bridge ordinary Source evidence into capability opportunities, without a model.

Reuse the native learner's witness collector. Host contexts provide independent
validation adapters and the task family, never a prewritten composition/DAG.
"""
from __future__ import annotations
import json
from pathlib import Path
from src.adapters.capability_contract import capability_digest, validate_capability_snapshot
from src.adapters.capability_feedback import file_ref, verify
from src.adapters.capability_discovery import read_context


def read(path):return json.loads(Path(path).read_text())


def inspect_run(entry,owner):
    run=Path(entry['run']).resolve();context=read_context(entry['context'],owner)
    if entry['role'] not in ('training','validation'):raise ValueError('discovery_heldout_prohibited')
    refs=[entry['context']]
    if entry['kind']=='native_source':
        effective=read(run/'effective.json');result=read(run/'result.json');task=effective['task']
        refs += [file_ref(run/name) for name in ('effective.json','result.json','events.jsonl')]
        status='failed';witness=None
        if result.get('status')=='completed':
            # Same source/receipt/media checks as the existing learning loop.
            from scenarios.remotion_edit.structured.learn_programs import collect
            witness,task=collect(run)
            refs.append(file_ref(run/'qa/verification.json'));status='passed'
            refs.append(file_ref(run/task['id']/'src/index.tsx'))
            refs.extend(file_ref(p) for p in sorted((run/task['id']/'out').glob('render-*/receipt.json')))
            if (run/'qa/semantic-review.json').exists():refs.append(file_ref(run/'qa/semantic-review.json'))
        elif result.get('status') not in ('failed','interrupted','error'):
            raise ValueError('discovery_terminal_run_required')
        identity=capability_digest({k:v for k,v in task.items() if k not in ('id','partition','arm_order')})
        trace={'task':task,'witness':witness,'status':status}
        task_id=task['id']
    elif entry['kind']=='capability_execution':
        trace=read(run/'trace.json');snapshot=validate_capability_snapshot(read(run/'snapshot.json'),owner)
        args=read(run/'args.json')
        if trace.get('owner')!=owner or trace.get('mode')!='execute' or trace.get('snapshot_sha256')!=snapshot['digest'] or trace.get('arguments_sha256')!=capability_digest(args):
            raise ValueError('discovery_execution_binding_changed')
        if trace.get('root') not in snapshot['roots']:raise ValueError('discovery_root_changed')
        refs += [file_ref(run/name) for name in ('trace.json','snapshot.json','args.json')]
        task_id=trace['task_id'];identity=capability_digest({'input':args,'scope':context['scope']})
        status='failed'
        if trace['status']=='succeeded':
            qa=read(run/'validation.json');refs.append(file_ref(run/'validation.json'))
            binding=qa.get('evidence_binding',{})
            for name in ('trace','manifest','specification'):
                ref=file_ref(run/(name+'.json'))
                if binding.get(name+'_sha256')!=ref['sha256']:raise ValueError('discovery_quality_binding_changed')
                refs.append(ref)
            if trace.get('manifest_sha256')!=binding['manifest_sha256']:raise ValueError('discovery_manifest_binding_changed')
            if qa.get('passed') is not True or not qa.get('checks') or any(c.get('status')!='passed' for c in qa['checks']):
                raise ValueError('discovery_quality_not_passed')
            status='passed'
        elif trace['status'] not in ('failed','rejected','interrupted'):raise ValueError('discovery_terminal_run_required')
    else:raise ValueError('discovery_adapter_unsupported')
    return {'task_id':task_id,'task_fingerprint':identity,'status':status,'scope':context['scope'],
            'kind':entry['kind'],'context':context,'evidence':refs,'trace':trace,'role':entry['role']}


def discover_jobs(entries,owner,directory,min_support=2):
    from src.adapters.capability_discovery import discover_jobs as discover
    return discover(entries,owner,directory,inspector=inspect_run,min_support=min_support)
