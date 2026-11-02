"""Scene-neutral discovery. Trusted adapters interpret native task evidence."""
from __future__ import annotations
import json
from pathlib import Path
from .capability_contract import capability_digest
from .capability_feedback import file_ref, verify


def read_context(ref,owner):
    context=json.loads(verify(ref))
    if set(context)!= {'owner','scope','contract','publication_plan'} or context['owner']!=owner or not context['scope']:
        raise ValueError('discovery_context_invalid')
    verify(context['publication_plan'])
    return context


def discover_jobs(entries,owner,directory,*,inspector,min_support=2):
    if type(min_support) is not int or min_support<2:raise ValueError('discovery_independent_support_required')
    directory=Path(directory);directory.mkdir(mode=0o700)
    groups={};ignored=[]
    for entry in entries:
        observation=inspector(entry,owner)
        if observation['role']!=entry['role'] or observation['role'] not in ('training','validation'):
            raise ValueError('discovery_heldout_prohibited')
        if observation['status'] not in ('passed','failed'):raise ValueError('discovery_terminal_run_required')
        if observation['context']!=read_context(entry['context'],owner):raise ValueError('discovery_context_changed')
        if not observation['evidence']:raise ValueError('discovery_evidence_required')
        for ref in observation['evidence']:verify(ref)
        context=observation['context']
        # Different independent validation plans are not silently pooled.
        key=capability_digest(context)
        groups.setdefault(key,[]).append(observation)
    jobs=[]
    for key,observations in groups.items():
        independent={o['task_fingerprint'] for o in observations}
        selected=list({capability_digest(o['evidence']):o for o in observations}.values())
        failed=any(o['status']=='failed' for o in selected)
        if len(independent)<min_support and not failed:
            ignored.append({'group':key,'reason':'insufficient_independent_tasks','support':len(independent)});continue
        identity=capability_digest([key,[o['evidence'] for o in selected]])
        job_id='discovered-'+identity[:20];context=selected[0]['context']
        task={'id':job_id,'instruction':'根据以下真实任务轨迹，构造可复用能力以处理同类当前输入。自行选择能力、参数流和输出；不得硬编码历史答案。失败证据可以帮助识别缺口，不能当作正确实现。该机会不是已证实的降本结果。',
              'contract':context['contract'],'learning_evidence':[o['trace'] for o in selected]}
        task_path=directory/(job_id+'-task.json');task_path.write_text(json.dumps(task,ensure_ascii=False,indent=2),encoding='utf-8');task_path.chmod(0o600)
        observation_rows=[]
        for index,o in enumerate(selected):
            path=directory/(job_id+'-evidence-'+str(index)+'.json')
            # Retain original references, not just copied summaries.
            path.write_text(json.dumps(o,ensure_ascii=False,indent=2),encoding='utf-8');path.chmod(0o600)
            observation_rows.append({'task_id':o['task_id'],'kind':'task_failure' if o['status']=='failed' else 'repeated_structure',
                'split':o['role'],'summary':'自动从场景真实记录提取；收益未知。','evidence':file_ref(path)})
        jobs.append({'id':job_id,'feedback_key':key,'execution_scope':context['scope'],'objective':'capability_acquisition','task':file_ref(task_path),
                     'publication_plan':context['publication_plan'],'observations':observation_rows,
                     'source_evidence':[ref for o in selected for ref in o['evidence']]})
    (directory/'discovery.json').write_text(json.dumps({'jobs':[j['id'] for j in jobs],'ignored':ignored},indent=2),encoding='utf-8')
    return jobs
