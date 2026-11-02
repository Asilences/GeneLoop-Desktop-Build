"""Bridge ordinary Source evidence into capability opportunities, without a model.

Reuse the native learner's witness collector. Host contexts provide independent
validation adapters and the task family, never a prewritten composition/DAG.
"""
from __future__ import annotations
import json
from pathlib import Path
from src.adapters.capability_contract import capability_digest, validate_capability_snapshot
from src.adapters.capability_feedback import file_ref, verify


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


def read_context(ref,owner):
    context=json.loads(verify(ref))
    if set(context)!= {'owner','scope','contract','publication_plan'} or context['owner']!=owner or not context['scope']:
        raise ValueError('discovery_context_invalid')
    verify(context['publication_plan'])
    return context


def discover_jobs(entries,owner,directory,min_support=2):
    if type(min_support) is not int or min_support<2:raise ValueError('discovery_independent_support_required')
    directory=Path(directory);directory.mkdir(mode=0o700)
    groups={};ignored=[]
    for entry in entries:
        observation=inspect_run(entry,owner)
        context=observation['context']
        # Different independent validation plans are not silently pooled.
        key=capability_digest(context)
        groups.setdefault(key,[]).append(observation)
    jobs=[]
    for key,observations in groups.items():
        independent={o['task_fingerprint']:o for o in observations}
        selected=list(independent.values())
        failed=any(o['status']=='failed' for o in selected)
        if len(selected)<min_support and not failed:
            ignored.append({'group':key,'reason':'insufficient_independent_tasks','support':len(selected)});continue
        identity=capability_digest([key,[o['evidence'] for o in selected]])
        job_id='discovered-'+identity[:20];context=selected[0]['context']
        task={'id':job_id,'instruction':'根据以下真实任务轨迹，构造可复用能力以处理同类当前输入。自行选择能力、参数流和输出；不得硬编码历史答案。失败证据可以帮助识别缺口，不能当作正确实现。该机会不是已证实的降本结果。',
              'contract':context['contract'],'learning_evidence':[o['trace'] for o in selected]}
        task_path=directory/(job_id+'-task.json');task_path.write_text(json.dumps(task,ensure_ascii=False,indent=2));task_path.chmod(0o600)
        observation_rows=[]
        for index,o in enumerate(selected):
            path=directory/(job_id+'-evidence-'+str(index)+'.json')
            # Retain original references, not just copied summaries.
            path.write_text(json.dumps(o,ensure_ascii=False,indent=2));path.chmod(0o600)
            observation_rows.append({'task_id':o['task_id'],'kind':'task_failure' if o['status']=='failed' else 'repeated_structure',
                'split':o['role'],'summary':'自动从场景真实记录提取；收益未知。','evidence':file_ref(path)})
        jobs.append({'id':job_id,'feedback_key':key,'execution_scope':context['scope'],'objective':'capability_acquisition','task':file_ref(task_path),
                     'publication_plan':context['publication_plan'],'observations':observation_rows,
                     'source_evidence':[ref for o in selected for ref in o['evidence']]})
    (directory/'discovery.json').write_text(json.dumps({'jobs':[j['id'] for j in jobs],'ignored':ignored},indent=2))
    return jobs
