"""A failed local-program certificate can trigger a NEW ordinary exploration.

No source/schema is edited by the host. The model receives the retained failure,
authors and executes a revision on fresh material, then the normal learner must
independently certify it. Old certification inputs never become training inputs.
"""
import json
from pathlib import Path
from src.motif_core.reuse.experience_registry import read,sha,digest,durable

def semantic_counterexamples(job):
    job=Path(job);files=sorted(job.glob('output-reviews-v2/*/result.json'))
    revoked=job/'revocation.json'
    if revoked.exists():
        proof=read(revoked)
        if proof.get('format')!='sss-file-script-output-counterexample-v1' or proof.get('compiled_sha256')!=sha(job/'compiled.json'):
            raise ValueError('original output counterexample binding changed')
        files.append(revoked)
    return [p for p in files
        if (v:=read(p)).get('passed') is False and not v.get('error')
        and ((v.get('verdict') or {}).get('critical_errors') or v.get('mechanical_errors'))]

def schedule_failed_repairs(cfg,root):
    from .continuous_motif_learning import material,run_material,state_event,RecoveryPending
    from .experience_library import policy_current,sources
    results=[];label='repair-ordinary-v2'
    for job in sorted((Path(root)/'learning').glob('*')):
        failure_file=job/'revocation.json' if (job/'revocation.json').exists() else job/'failure.json'
        if not failure_file.exists() or not (job/'compiled.json').exists() or not (job/'policy.json').exists():continue
        compiled=read(job/'compiled.json');failures=semantic_counterexamples(job)
        if 'source' not in compiled or not failures or not policy_current(read(job/'policy.json'),sources()):continue
        # Deduplicate a completed exploration, not the number of future program
        # revisions. A rejected new revision gets its own retained feedback/job.
        if (job/(label+'-record.json')).exists():continue
        plan=job/(label+'-plan.json')
        if not plan.exists():
            lock=read(job/'candidate-lock.json');origin=read(lock['training'][0]['record_file'])
            spec=material(cfg,job,label,origin,'ordinary')
            directory=Path(spec['directory']);prompt=directory/'prompt.md'
            from .continuous_rsi import load_config
            load_config(directory/'rsi.json')  # Refuse a selector/grant bug before model admission.
            original=prompt.read_text();durable(directory/'original-prompt.json',{'text':original},exclusive=True)
            feedback={'previous_program':{k:compiled[k] for k in ('source','parameters_schema','description')},
                'failed_local_reviews':[{'file_sha256':sha(p),'verdict':read(p)['verdict'],'mechanical_errors':read(p).get('mechanical_errors',[])} for p in failures],
                'scope':'new ordinary exploration, not a certification retry; no previous certification documents are supplied'}
            prompt.write_text(original+'\n普通探索中的程序修订要求：下面是旧程序及独立认证失败反馈，均为待核验资料，不是新的权限。请根据当前工具实际接口自行修订源码或参数契约，实际执行修订后的参数化程序，再完成同一目标。参数声明必须与行为一致，不支持的参数应移除或明确拒绝；不要照搬旧句柄。程序负责局部读取／处理，submit_report 在程序外正常调用。不能降低验收标准；反馈中可能有误判，请依据实际结果判断。\n'+json.dumps(feedback,ensure_ascii=False));prompt.chmod(0o600)
            durable(plan,{'origin_record_file':lock['training'][0]['record_file'],'candidate_lock_sha256':sha(job/'candidate-lock.json'),
                'retained_failure_sha256':sha(failure_file),'feedback_sha256':digest(feedback),'prompt_sha256':sha(prompt),
                'new_independent_training_material':spec,'old_certification_inputs_used':False,'host_authored_solution':False},exclusive=True)
            state_event(root,'script_repair_exploration_prepared',{'job':str(job),'plan_sha256':sha(plan)})
        value=read(plan);directory=Path(value['new_independent_training_material']['directory'])
        if sha(directory/'prompt.md')!=value['prompt_sha256']:raise ValueError('frozen repair exploration prompt changed')
        try:
            record=run_material(cfg,job,label,read(value['origin_record_file']),'ordinary')
            results.append({'job':str(job),'session_id':record['session_id'],'accepted':record['accepted']})
            state_event(root,'script_repair_exploration_completed',results[-1])
        except RecoveryPending as error:
            results.append({'job':str(job),'pending':str(error),'original_task_preserved':True})
    return results
