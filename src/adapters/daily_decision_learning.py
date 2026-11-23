"""Daily capture, learning and admission of model-authored decision programs.

Uses the existing compiler, task runner, account meter and experience store.
Certification consumes later ordinary tasks, never the two teacher tasks or a
benchmark. Only private certification copies receive an unactivated candidate.
"""
import json
import os
import shutil
import sys
from pathlib import Path
from uuid import uuid4

from src.motif_core.reuse.experience_registry import read, sha, digest, durable

RUNTIME = ['src/adapters/harness/learning/dsh_learned_decisions.ts', 'src/adapters/learned_decision_program.ts',
           'src/adapters/paper_rsi_program.ts', 'src/adapters/file_read_evidence.ts',
           'src/adapters/typed_decisions.ts', 'src/adapters/typed_decision_resolution.ts',
           'src/adapters/kouri_jev.ts', 'src/adapters/decision_accounting.py', 'scripts/decision-meter.py',
           'src/adapters/file_management/file_recovery_state.ts', 'src/adapters/harness/learning/dsh_file_resume.ts',
           'src/adapters/file_management/file_decision_checkpoint.ts']


def enabled(cfg):
    return (os.name == 'posix' and bool(os.environ.get('SSS_FILE_PROVIDER_CONFIG'))
            and cfg.get('adapter') == 'management_v3' and cfg['provider_mode'] == 'real'
            and cfg['mode'] == 'learn' and cfg.get('decision_programs', True))


def runtime_sources():
    from .continuous_rsi import ROOT
    return {n: sha(ROOT/n) for n in RUNTIME}


def plugin(cfg, spec, out, *, task_budget_usd, candidate=None):
    """Freeze the catalogue and original account binding in the durable RSI patch."""
    from .continuous_rsi import ROOT, PRIVATE_HOME
    state = Path(cfg['state_root']); out = Path(out)
    pointer = state/'experience/current.json'
    catalog = state/'experience'/read(pointer)['file'] if pointer.exists() else None
    if catalog is None:
        catalog = out/'decision-empty-catalog.json'
        durable(catalog, {'jobs': []}, exclusive=True)
    provider = os.environ.get('SSS_FILE_PROVIDER_CONFIG')
    # Unknown-price decisions cannot be admitted to a finite grant. Capture is
    # still useful and does not enlarge that grant or make a paid side request.
    admitted = (provider and task_budget_usd is None and cfg['limits']['budget_usd'] is None
                and all(cfg.get(k) is None for k in ('series_cap_usd', 'learning_cap_usd')))
    meter = out/'decision-meter-context.json'
    durable(meter, {'format': 'geneloop-decision-account-v1', 'private_root': str(PRIVATE_HOME),
        'state_root': str(state), 'owner': spec['owner'], 'original_config': cfg['config_file']}, exclusive=True)
    config = {'mode': 'execute' if admitted else 'capture', 'provider': 'jev',
        'scene': 'files', 'source_mode': 'harness_plus_motif', 'state_root': str(state),
        'runtime_sources': runtime_sources(), 'python': sys.executable,
        'meter_context': str(meter), 'record_root': str(PRIVATE_HOME/'decision-calls'),
        'provider_config': provider, 'catalog_file': str(catalog), 'catalog_sha256': sha(catalog),
        'expected_models': {'jev': 'jev-1.14.0', 'deepseek': 'deepseek-v4.1-flash'}}
    if candidate:
        config.update(candidate_file=str(candidate), candidate_sha256=sha(candidate))
    return {'id': 'geneloop-learned-decisions',
            'name': (ROOT/'src/adapters/harness/learning/dsh_learned_decisions.ts').as_uri(), 'config': config}


def _retired_decision_sources(state, job, owner, root, current_sources, private):
    if job.get('state') != 'active':
        return False
    try:
        path = private(state / job['job'] / 'activation.json')
        activation = read(path)
        if (activation.get('kind') != 'learned_decision_recipe' or activation.get('owner') != owner
                or (path.parent / 'suspension.json').exists()):
            return False
        payload_file = private(activation['payload_file'])
        proof_file = private(activation['certificate_file'])
        if (sha(payload_file) != activation['payload_sha256']
                or sha(proof_file) != activation['certificate_sha256']):
            return False
        payload, proof = read(payload_file), read(proof_file)
        base = proof.get('base_source_map')
        runtime = payload['runtime_sources']
        if (proof.get('status') != 'certified' or proof.get('owner') != owner
                or proof.get('payload_sha256') != activation['payload_sha256']
                or not isinstance(base, dict) or proof['runtime_sources'] != {**base, **runtime}):
            return False
        for name in base.keys() - runtime.keys() - current_sources:
            source = Path(name)
            if not source.is_absolute() and '..' not in source.parts and not (root / source).exists():
                return True
    except (OSError, ValueError, KeyError, TypeError):
        # The runtime still handles corrupt or changed activation objects.
        return False
    return False


def compatible_decision_config(config, out, *, owner, refresh_cfg=None):
    """Project retired certification rows out of the frozen task catalogue."""
    from .continuous_rsi import LEARNER, ROOT, private

    if config['mode'] != 'execute' or config.get('candidate_file'):
        return config

    state = Path(config['state_root'])
    catalogue = private(config['catalog_file'])
    if sha(catalogue) != config['catalog_sha256']:
        raise ValueError('frozen experience catalogue changed')
    current_sources = set(LEARNER)

    def project(path):
        value = read(path)
        jobs = value.get('jobs') or []
        value['jobs'] = [job for job in jobs
                         if not _retired_decision_sources(state, job, owner, ROOT, current_sources, private)]
        return value, len(jobs) != len(value['jobs'])

    value, filtered = project(catalogue)
    if not filtered:
        return config

    if refresh_cfg is not None and refresh_offline_compatible(refresh_cfg):
        pointer = state / 'experience/current.json'
        if pointer.exists():
            catalogue = private(state / 'experience' / read(pointer)['file'])
            value, filtered = project(catalogue)
    if filtered:
        catalogue = Path(out) / 'decision-compatible-catalog.json'
        durable(catalogue, value, exclusive=True)
    return {**config, 'catalog_file': str(catalogue), 'catalog_sha256': sha(catalogue)}


def run_plugin(cfg, spec, out, *, task_budget_usd, candidate=None):
    registration = plugin(cfg, spec, out, task_budget_usd=task_budget_usd, candidate=candidate)
    registration['config'] = compatible_decision_config(registration['config'], out, owner=spec['owner'], refresh_cfg=cfg)
    return registration


def eligible_records(cfg):
    from .continuous_rsi import records
    result = []
    for record in records(cfg['state_root']):
        origin = Path(record['origin'])
        spec = read(origin/'task.json')
        if (record['role'] == 'ordinary' and record['provider_mode'] == 'real'
                and record['accepted'] and record['accounting_complete'] and record['lifecycle_verified']
                and spec.get('learning_eligible') is True and not spec.get('external_roots')
                and (Path(record['run_dir'])/'decision-captures').exists()):
            enrollment = origin/'enrollment.json'
            patch = Path(record['run_dir'])/'rsi.patch.yml'
            if not enrollment.is_file() or not patch.is_file():
                continue
            original = read(enrollment).get('arguments', {})
            if 'budget_usd' not in original or original['budget_usd'] is not None:
                continue
            configured=[p for row in read(patch) for p in row.get('insert',[])if p.get('id')=='geneloop-learned-decisions']
            if len(configured)==1 and configured[0]['config']['runtime_sources']==runtime_sources():
                result.append(record)
    return sorted(result, key=lambda r: Path(r['origin']).stat().st_mtime)


def opportunities(cfg, values):
    from .learned_decision_learning import source_opportunities
    result = {'format': 'geneloop-native-decision-opportunities-v2', 'opportunities': [], 'excluded': []}
    for record in values:
        try:
            bundle = source_opportunities([Path(cfg['state_root'])/'records'/(record['session_id']+'.json')],
                                          include_history=True, allow_auxiliary_todo=True)
            result['opportunities'].extend(bundle['opportunities']); result['excluded'].extend(bundle['excluded'])
        except (ValueError, KeyError) as error:
            result['excluded'].append({'session_id': record['session_id'], 'reason': str(error)})
    return result


def generation(cfg, job, bundle):
    from .learned_decision_learning import (discover_indexed, generate_from_selection,
        compile_candidate, repair_compile_candidate, revise_components, generated_candidate)
    from .learned_decision_certificate import file_source_guard_checks
    from .empirical_decision_certificate import check_empirical_guards
    from src.motif_core.offline.compilation.decision_program_lowering import VERSION
    sources = job/'source-opportunities.json'
    if not sources.exists():durable(sources, bundle, exclusive=True)
    owner = read(Path(read(bundle['opportunities'][0]['record_file'])['origin'])/'task.json')['owner']
    selection_file=job/'selection-1/result.json'
    selection = read(selection_file) if selection_file.exists() else discover_indexed(cfg['config_file'], sources, job, iteration=1,
                                 selection_only=True, model='deepseek-v4-pro', daily_programs=True)
    if selection['status'] != 'completed' or not selection.get('answer', {}).get('selected_snapshot_ids'):
        return {'status': 'no_candidate', 'selection': selection.get('answer'), 'error': selection.get('error')}
    selected_ids = set(selection['answer']['selected_snapshot_ids'])
    selected = {'opportunities': [s for s in bundle['opportunities'] if s['snapshot_id'] in selected_ids]}
    if (len(selected_ids)!=len(selected['opportunities']) or len({s['session_id']for s in selected['opportunities']})<2):
        raise ValueError('cached automatic selection must still cite two actual independent sources')
    selected_file = job/'selected-sources.json'
    if not selected_file.exists():durable(selected_file, selected, exclusive=True)
    # Model-authored previous programs are prototypes, never host-written task
    # routes. A suspended program cannot be a prototype or regain activation.
    prototypes = []
    from .learned_decision_certificate import replay
    for activation in (Path(cfg['state_root'])/'experience/jobs').glob('*/activation.json'):
        if (activation.parent/'suspension.json').exists():continue
        a = read(activation)
        if a.get('kind') != 'learned_decision_recipe' or a.get('owner') != owner:continue
        value = read(a['payload_file'])
        try:
            if generated_candidate(value['model_generation_file']) == value['candidate']:
                applicable=0
                for source in selected['opportunities']:
                    try:
                        if (source['native_call']['tool'] in value['tool_schema_hashes']
                                and replay(value['candidate'],source['context'],{},preparation_probe=True).get('request')):
                            applicable+=1
                    except (ValueError,KeyError,TypeError):pass
                prototypes.append((applicable,activation.stat().st_mtime,value))
        except (ValueError, KeyError, OSError):continue
    if prototypes:
        base = max(prototypes,key=lambda p:(p[0],p[1]))[2]; feedback = job/'transfer-feedback.json'
        if not feedback.exists():durable(feedback, {'reason': 'Learn from new real task decisions using existing verified program experience.',
            'requirements': 'Parameterize current evidence, preserve working components when applicable, revise actual witnesses and synchronise description/scope with executable guard. Choose direct execution only when no semantic judgment remains. No certification inputs are supplied.'}, exclusive=True)
        from .learned_decision_certificate import replay
        first=max([int(p.name.split('-')[-1])for p in job.glob('patch-*')if p.name.split('-')[-1].isdigit()]+[0])+1
        components=['training_witnesses','description','scope_description']
        seen=set();iteration=first
        while True:
            outcome = revise_components(cfg['config_file'], base['model_generation_file'], feedback, job, iteration,
                owner, runtime_sources(), selected_file, components=components, structured_output=True, program_notation=VERSION,
                empirical=True, source_extension_file=selected_file, daily_programs=True)
            result_file = job/('revision-'+str(iteration))/'result.json'
            if outcome['status']=='generation_failed':
                raw=outcome['model_result'];error=raw.get('error')or{}
                if error.get('type')!='ValidationError':return {'status':'generation_failed','detail':outcome}
                signature=digest({'answer':raw.get('answer'),'error':error})
                if signature in seen:return {'status':'generation_no_progress','detail':outcome}
                seen.add(signature);iteration+=1;feedback=job/('transfer-feedback-'+str(iteration)+'.json')
                durable(feedback,{'actual_model_schema_error':error,'original_model_answer':raw.get('answer'),
                    'instruction':'Return only the declared replacement components. tool/arguments belong inside bind, never at candidate_patch root. Keep unchanged executable components when applicable.'},exclusive=True)
                continue
            if outcome['status']=='compiled':
                candidate=read(outcome['payload_file'])['candidate'];sources_by_id={s['snapshot_id']:s for s in selected['opportunities']}
                usable=[]
                for w in candidate['training_witnesses']:
                    source=sources_by_id[w['snapshot_id']]
                    binding=replay(candidate,source['context'],w['values']).get('binding')
                    if binding and binding['tool']==source['native_call']['tool']:usable.append(w)
                if len({sources_by_id[w['snapshot_id']]['session_id']for w in usable})>=2:break
                # Transfer first; only regenerate executable components when
                # their actual preparation/binding fails on the new teachers.
                components=['guard','request','bind','training_witnesses','description','scope_description']
                iteration+=1;feedback=job/('transfer-feedback-'+str(iteration)+'.json')
                durable(feedback,{'reason':'Existing executable does not produce a usable request/binding on two current teachers; learn the necessary executable changes from the supplied real sources.'},exclusive=True)
                continue
            break
    else:
        generate_from_selection(cfg['config_file'], sources, job/'selection-1/result.json', job, 1,
                                model='deepseek-v4-pro', daily_programs=True)
        result_file = job/'proposal-1/result.json'
    payload = job/('payload-'+str(iteration if prototypes else 1)+'.json')
    try:compile_candidate(result_file, selected_file, payload, owner, runtime_sources(), empirical=True)
    except (ValueError, KeyError, TypeError):
        repair = repair_compile_candidate(cfg['config_file'], result_file, selected_file, job/'repair', owner, runtime_sources())
        if repair['status'] != 'compiled':return repair
        payload = Path(repair['payload_file'])
    guard = job/('guard-checks-'+sha(payload)+'.json')
    if not guard.exists():file_source_guard_checks(payload, selected_file, guard, preparation_probe=True)
    check_empirical_guards(payload, guard)
    value = read(payload)
    return {'status': 'awaiting_independent_tasks', 'payload_file': str(payload), 'guard_file': str(guard),
            'training_sessions': sorted({s['session_id'] for s in bundle['opportunities']}),
            'training_hashes': sorted({h for s in bundle['opportunities']
                for n,h in read(Path(read(s['record_file'])['origin'])/'task.json')['initial_tree']['workspace']['files'].items() if not n.startswith('.')}),
            'runtime_sources': runtime_sources(), 'base_source_map': __import__('src.adapters.continuous_rsi', fromlist=['source_map']).source_map(),
            'certifications': [], 'attempted_certification_sessions': []}


def certify(cfg, job, record, state):
    from types import SimpleNamespace
    from .continuous_rsi import ROOT
    from .scenario import prepare_file_scenario as prepare_scenario
    from .operation_runner import execute
    from .learned_decision_certificate import execution_evidence, local_review, reviewed
    from .file_management.decision_trial_judge import judge
    from .empirical_decision_certificate import LOCAL_SYSTEM
    directory = job/'certification'/record['session_id']; directory.mkdir(parents=True, exist_ok=True, mode=0o700)
    original = Path(record['origin']); spec = read(original/'task.json')
    if spec.get('external_roots'):raise ValueError('independent certification cannot extend external access')
    if not (directory/'definition.json').exists():
        work = Path(cfg['workspace_roots'][0])/'decision-certification'/job.name/record['session_id']
        if work.exists():raise ValueError('partial material retained; inspect original certification copy')
        shutil.copytree(original/'pristine', work)
        spec.update(task_id='decision-cert-'+uuid4().hex, workspace=str(work), learning_eligible=False)
        task = directory/'input.json'; durable(task, spec, exclusive=True)
        enrolled = read(original/'enrollment.json'); prompt = directory/'prompt.md'
        prompt.write_text(enrolled['prompt']); prompt.chmod(0o600)
        scenario = read(enrolled['scenario_file']); scenario['prompt'] = str(prompt)
        scenario['acceptance_guard']['max_repairs'] = cfg['limits']['max_repairs']
        durable(directory/'scenario.json', scenario, exclusive=True)
        child = {k:v for k,v in cfg.items() if k not in ('config_file','config_sha256','registry_file','candidate_job')}
        child.update(role='native_certification', auto_worker=False, decision_programs=True)
        durable(directory/'rsi.json', child, exclusive=True)
        durable(directory/'definition.json', {'task': str(task), 'config': str(directory/'rsi.json'),
            'file_sources': {n: {'source': 'independent later ordinary task', 'input_scope': 'complete authorized task copy'}
                             for n in spec['initial_tree']['workspace']['files'] if not n.startswith('.')},
            'independent_original_session': record['session_id']}, exclusive=True)
    os.environ.update(FM_TASK_FILE=str(directory/'input.json'), FM_OUTPUT=str(directory/'delivery'))
    # Background certification has no inherited browser high-risk approval.
    os.environ.pop('HARLESS_FILE_APPROVAL_HOME', None)
    payload = state['payload_file']; args = SimpleNamespace(call_model=True,
        rsi_resume=Path(read(directory/'enrollment.json')['origin']) if (directory/'enrollment.json').exists() else None,
        rsi_config=directory/'rsi.json', scenario=directory/'scenario.json', model='deepseek-v4-pro',
        budget_usd=cfg['limits']['budget_usd'], max_steps=cfg['limits']['max_steps'], max_output=cfg['limits']['max_output'])
    if not (directory/'result.json').exists():
        prepared = prepare_scenario(args.scenario, web_deployment=True)
        prepared['decision_candidate'] = payload
        r = execute(args, prepared, on_start=lambda context: durable(directory/'enrollment.json', context))
        audit = Path(r['output_dir'])/'learned-decision-audit.jsonl'
        r['learned_events'] = [json.loads(l) for l in audit.read_text().splitlines()] if audit.exists() else []
        if r['status'] == 'interrupted':return {'status': 'interrupted', 'result': r, 'directory': str(directory)}
        durable(directory/'result.json', r, exclusive=True)
    result = directory/'result.json'; proof = execution_evidence(payload, result, cfg['state_root'], allow_task_repairs=True)
    if not proof['local']:raise ValueError('independent task had no actual program substitution')
    local = local_review(cfg['config_file'], payload, result, cfg['state_root'], directory/'local-review',
                         allow_task_repairs=True, review_system=LOCAL_SYSTEM)
    if not reviewed(local):raise ValueError('independent local decision review failed')
    files=[];index=0
    while len(files)<2:
        index+=1;existing=directory/'blind-judge-v5'/str(index)/'result.json'
        if existing.exists() and read(existing)['status']=='failed':continue
        review=judge(cfg['config_file'],directory,index,http_timeout=900)
        if review['status']=='completed':files.append(str(directory/'blind-judge-v5'/str(index)/'result.json'))
        else:return {'status':'review_interrupted','directory':str(directory)}
    if not all(read(f)['passed'] for f in files):raise ValueError('independent whole task review failed')
    return {'status':'passed','result':str(result),'local_review':str(directory/'local-review/result.json'),'whole_reviews':files}


def _drain_once(config_file):
    from .continuous_rsi import load_config, writer_lock, state_event, source_map
    cfg=load_config(config_file); root=Path(cfg['state_root'])
    if not enabled(cfg):return {'status':'disabled'}
    if (not os.environ.get('SSS_FILE_PROVIDER_CONFIG') or any(cfg.get(k) is not None for k in ('series_cap_usd','learning_cap_usd'))
            or cfg['limits']['budget_usd'] is not None):
        return {'status':'capture_only','reason':'A configured semantic provider and the existing unpriced-call grant are required; original finite grants remain unchanged.'}
    if not cfg.get('allow_material_copy'):
        return {'status':'awaiting_material_copy_grant','original_permissions_unchanged':True}
    home=root/'decision-learning'; home.mkdir(parents=True,exist_ok=True,mode=0o700)
    with writer_lock(root,'decision-worker'):
        refresh_offline_compatible(cfg)
        suspended=suspend_failed_executions(cfg)
        values=eligible_records(cfg); current=home/'current.json'; state=read(current) if current.exists() else None
        if state and state.get('activation',{}).get('payload_sha256') in suspended:
            state['status']='suspended';durable(current,state)
        fingerprint=digest({'records':[r['session_id'] for r in values],'runtime':runtime_sources(),'source':source_map()})
        terminal=('active','already_available','no_candidate','failed','waiting_for_sources','suspended')
        resume_generation=bool(state and state['status']=='failed' and state.get('generation_outcome')
                               and (Path(state['job'])/'source-opportunities.json').exists())
        if state and state.get('fingerprint')==fingerprint and state['status'] in terminal:
            return state
        if state and state.get('runtime_sources'):
            if state['runtime_sources']!=runtime_sources():
                state=None  # Changed program execution semantics need new learning.
            elif state['base_source_map']!=source_map():
                if state['status']=='awaiting_independent_tasks' and not state['certifications']:
                    # An uncertified, unchanged pure program can receive its
                    # FIRST independent certification under the updated host.
                    # No old certificate, source, score or program is rewritten.
                    transition=Path(state['job'])/'host-transitions'/(digest(source_map())+'.json')
                    if not transition.exists():durable(transition,{'old_source_map':state['base_source_map'],
                        'new_source_map':source_map(),'pure_runtime_unchanged':True,
                        'no_prior_certification_reused':True},exclusive=True)
                    state['base_source_map']=source_map()
                else:state=None
        job=Path(state['job']) if state and (state['status'] not in terminal or resume_generation) else home/'jobs'/fingerprint
        job.mkdir(parents=True,exist_ok=True,mode=0o700)
        try:
            if not state or state['status'] in terminal:
                bundle=read(job/'source-opportunities.json') if resume_generation else opportunities(cfg,values)
                if len({s['session_id'] for s in bundle['opportunities']})<2:
                    state={'status':'waiting_for_sources'}
                else:
                    state=generation(cfg,job,bundle)
                    if state['status'] not in ('awaiting_independent_tasks','no_candidate'):
                        state={'status':'failed','generation_outcome':state,'original_costs_and_failures_retained':True}
                state.update(job=str(job),fingerprint=fingerprint)
                durable(current,state); durable(job/'state.json',state)
            if state['status']!='awaiting_independent_tasks':return state
            if not valid_training_roots(read(state['payload_file']),job/'selected-sources.json'):
                state.update(status='failed',error='Generated program does not implement the selected native tool roots; candidate stays inactive.',fingerprint=fingerprint)
                durable(current,state);durable(job/'state.json',state);return state
            equivalent=equivalent_active(cfg,read(state['payload_file']))
            if equivalent:
                state.update(status='already_available',activation=equivalent,
                    duplicate_execution_program_not_published=True,fingerprint=fingerprint)
                durable(current,state);durable(job/'state.json',state)
                return state
            from .learned_decision_certificate import replay
            for record in values:
                sid=record['session_id']
                if sid in state['training_sessions'] or sid in state['attempted_certification_sessions']:continue
                spec=read(Path(record['origin'])/'task.json'); hashes={h for n,h in spec['initial_tree']['workspace']['files'].items() if not n.startswith('.')}
                if hashes & set(state['training_hashes']):continue
                bundle=opportunities(cfg,[record]); candidate=read(state['payload_file'])['candidate']
                if not any(replay(candidate,s['context'],{},preparation_probe=True).get('request') for s in bundle['opportunities']):continue
                review=certify(cfg,job,record,state)
                if review['status'] in ('interrupted','review_interrupted'):
                    state['recovery_pending']=review;break
                state['attempted_certification_sessions'].append(sid);state['certifications'].append(review)
                durable(current,state);durable(job/'state.json',state)
                if len(state['certifications'])>=2:
                    from .empirical_decision_certificate import publish_empirical
                    rows=state['certifications'];activation=publish_empirical(cfg['config_file'],state['payload_file'],
                        [r['result']for r in rows],[r['local_review']for r in rows],
                        [r['whole_reviews'][0]for r in rows],state['guard_file'],daily_file=True)
                    state.update(status='active',activation=activation);break
        except (ValueError,KeyError,TypeError,RuntimeError,OSError) as error:
            state={**(state or {}),'status':'failed','error':type(error).__name__+': '+str(error),
                   'job':str(job),'fingerprint':fingerprint,'original_costs_and_failures_retained':True}
        state['fingerprint']=fingerprint
        durable(job/'state.json',state);durable(current,state)
        state_event(root,'daily_decision_learning',state)
        return state


def drain(config_file):
    from .continuous_rsi import load_config
    cfg=load_config(config_file)
    while True:
        before=[r['session_id']for r in eligible_records(cfg)] if enabled(cfg) else []
        result=_drain_once(config_file)
        after=[r['session_id']for r in eligible_records(cfg)] if enabled(cfg) else []
        if before==after:return result


def summary(root):
    from .continuous_rsi import ROOT
    file=Path(root)/'decision-learning/current.json'
    result=read(file) if file.exists() else {'status':'waiting_for_sources'}
    active=set()
    for path in (Path(root)/'experience/jobs').glob('*/activation.json'):
        if (path.parent/'suspension.json').exists():continue
        a=read(path)
        if a.get('kind')!='learned_decision_recipe':continue
        proof=read(a['certificate_file'])
        if proof.get('status')=='certified' and all((ROOT/n).exists()and sha(ROOT/n)==h for n,h in proof['runtime_sources'].items()):
            active.add(executable_digest(read(a['payload_file'])))
    return {**result,'active_programs':len(active),'candidate_failure_does_not_disable_unrelated_active_programs':True}


def executable_digest(value):
    return digest({'program':{k:value['candidate'][k]for k in ('guard','request','bind')},
        'threshold':value['threshold'],'tools':value['tool_schema_hashes'],'runtime':value['runtime_sources']})


def valid_training_roots(payload,source_file):
    from .learned_decision_certificate import replay
    by_id={s['snapshot_id']:s for s in read(source_file)['opportunities']};matched=set()
    for witness in payload['candidate']['training_witnesses']:
        source=by_id[witness['snapshot_id']]
        binding=replay(payload['candidate'],source['context'],witness['values']).get('binding')
        if binding and binding['tool']==source['native_call']['tool'] and binding['tool']in payload['tool_schema_hashes']:
            matched.add(source['session_id'])
    return len(matched)>=2


def equivalent_active(cfg,payload):
    from .continuous_rsi import ROOT
    for file in (Path(cfg['state_root'])/'experience/jobs').glob('*/activation.json'):
        if (file.parent/'suspension.json').exists():continue
        a=read(file)
        if a.get('kind')!='learned_decision_recipe' or a.get('owner')!=payload['owner']:continue
        if sha(a['payload_file'])!=a['payload_sha256'] or sha(a['certificate_file'])!=a['certificate_sha256']:continue
        proof=read(a['certificate_file']);value=read(a['payload_file'])
        if proof.get('status')!='certified' or any(not(ROOT/n).exists()or sha(ROOT/n)!=h for n,h in proof['runtime_sources'].items()):continue
        if executable_digest(value)==executable_digest(payload):return a
    return None


def same_online_hooks(old_source,new_source):
    import ast
    def hooks(source):
        tree=ast.parse(source)
        value={n.name:ast.dump(n,include_attributes=False)for n in tree.body
               if isinstance(n,(ast.FunctionDef,ast.AsyncFunctionDef))and n.name in ('enabled','plugin','runtime_sources')}
        value['imports']=[ast.dump(n,include_attributes=False)for n in tree.body if isinstance(n,(ast.Import,ast.ImportFrom))]
        value['runtime_constants']=[ast.dump(n,include_attributes=False)for n in tree.body if isinstance(n,ast.Assign)
            and any(isinstance(t,ast.Name)and t.id=='RUNTIME'for t in n.targets)]
        return value
    a,b=hooks(old_source),hooks(new_source)
    return all(k in a for k in ('enabled','plugin','runtime_sources')) and a==b


def refresh_offline_compatible(cfg):
    """Append a compatibility wrapper after exact source checks."""
    from .continuous_rsi import ROOT, reviewed_source_relocation, source_map, writer_lock
    from .experience_library import synchronize
    from src.motif_core.reuse.experience_registry import ExperienceRegistry
    root=Path(cfg['state_root']);name='src/adapters/daily_decision_learning.py';changed=[]
    with writer_lock(root,'state'):
        seen=set()
        current_source = source_map()
        files=sorted((root/'experience/jobs').glob('*/activation.json'),key=lambda p:p.stat().st_mtime,reverse=True)
        for file in files:
            if (file.parent/'suspension.json').exists():continue
            a=read(file)
            if a.get('kind')!='learned_decision_recipe':continue
            if sha(a['payload_file'])!=a['payload_sha256']or sha(a['certificate_file'])!=a['certificate_sha256']:continue
            payload=read(a['payload_file']);proof=read(a['certificate_file'])
            if any(not(ROOT/n).exists()or sha(ROOT/n)!=h for n,h in payload['runtime_sources'].items()):continue
            key=(a['owner'],executable_digest(payload))
            if key in seen:continue
            expected = {**current_source, **payload['runtime_sources']}
            recorded = proof['runtime_sources']
            if recorded == expected:
                seen.add(key);continue
            differences = {n for n in recorded.keys() | expected.keys() if recorded.get(n) != expected.get(n)}
            before = proof.get('base_source_map')
            relocated = (isinstance(before, dict) and recorded == {**before, **payload['runtime_sources']}
                         and reviewed_source_relocation(before, current_source))
            if not relocated:
                if set(recorded) != set(expected) or differences != {name}:
                    continue
                previous = proof.get('host_compatibility', {}).get('source_file')
                if not previous:
                    previous = Path(read(proof['reviews'][0]['record_file'])['origin']) / 'frozen-source' / name
                previous = Path(previous)
                if not previous.exists() or sha(previous) != recorded[name]:
                    continue
                if not same_online_hooks(previous.read_text(), (ROOT / name).read_text()):
                    continue
            compatibility={'parent_payload_sha256':a['payload_sha256'],'parent_certificate_file':a['certificate_file'],
                'parent_certificate_sha256':a['certificate_sha256'],'changed_offline_files':sorted(differences),
                'online_hooks_and_pure_runtime_unchanged':True,'new_independent_certification':False}
            new_payload={**payload,'host_compatibility':compatibility}
            # Registry.object hashes the exact JSON bytes written here.
            stage=root/'decision-learning/compatibility'/digest(compatibility);stage.mkdir(parents=True,exist_ok=True,mode=0o700)
            pf=stage/'payload.json'
            if not pf.exists():durable(pf,new_payload,exclusive=True)
            source=stage/'source.py'
            if not source.exists():shutil.copy2(ROOT/name,source);source.chmod(0o600)
            new_proof={**proof,'payload_sha256':sha(pf),'runtime_sources':expected,'base_source_map':current_source,
                'host_compatibility':{**compatibility,'source_file':str(source),'source_sha256':sha(source)}}
            cf=stage/'certificate.json'
            if not cf.exists():durable(cf,new_proof,exclusive=True)
            store=ExperienceRegistry(root/'experience');pfile,ph=store.object(pf);cfile,ch=store.object(cf)
            job=root/'experience/jobs'/('learned-decision-'+ph);job.mkdir(parents=True,exist_ok=True,mode=0o700)
            target=job/'activation.json'
            if not target.exists():durable(target,{**a,'payload_file':str(root/'experience'/pfile),'payload_sha256':ph,
                'certificate_file':str(root/'experience'/cfile),'certificate_sha256':ch,
                'compatibility_only':True,'new_native_motif_entries':0},exclusive=True)
            seen.add(key)
            changed.append(ph)
    if changed:synchronize(cfg)
    return changed


def suspend_failed_executions(cfg):
    """A real failed task with an executed recipe is a counterexample, not a fee signal."""
    from .continuous_rsi import records, state_event
    root=Path(cfg['state_root']);suspended=[]
    for record in records(root):
        if record['role']!='ordinary' or record['accepted'] or record.get('failure_class') in ('provider_unavailable','budget_exhausted','cancelled'):continue
        audit=Path(record['run_dir'])/'learned-decision-audit.jsonl'
        if not audit.exists():continue
        ids={e['candidate']for e in [json.loads(l)for l in audit.read_text().splitlines()]if e['kind']=='learned_decision_tool_bound'}
        for activation in (root/'experience/jobs').glob('*/activation.json'):
            a=read(activation)
            if a.get('kind')!='learned_decision_recipe' or read(a['payload_file'])['candidate_sha256']not in ids:continue
            marker=activation.parent/'suspension.json'
            if marker.exists():continue
            durable(marker,{'format':'geneloop-learned-decision-suspension-v1','payload_sha256':a['payload_sha256'],
                'evidence_sha256':sha(root/'records'/(record['session_id']+'.json')),
                'reason':'Actual ordinary task failed after executing this program; preserve native repair trace and certify a changed revision.'},exclusive=True)
            suspended.append(a['payload_sha256'])
    if suspended:state_event(root,'daily_decision_program_suspended',{'payloads':suspended})
    return suspended
