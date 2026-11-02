"""Offline improvement coordinator. Harness owns model turns, TS owns execution.

Host adapters supply pinned observations and independent publication. No model
proposal can choose a validator, award a certificate, or change this policy.
"""
from __future__ import annotations
import copy
import hashlib
import json
import os
from pathlib import Path
from jsonschema import Draft202012Validator
from src.adapters.capability_contract import capability_digest, capability_ref, validate_capability_snapshot

ROOT = Path(__file__).resolve().parents[2]
SCHEMA = json.loads((ROOT/'schemas/capability-improvement-v1.schema.json').read_text(encoding='utf-8'))


def validate(kind, value):
    Draft202012Validator({'$ref': '#/$defs/'+kind, '$defs': SCHEMA['$defs']}).validate(value)
    return value


def save(path, value):
    with Path(path).open('x', encoding='utf8') as f:
        os.chmod(path, 0o600)
        json.dump(value, f, ensure_ascii=False, allow_nan=False, indent=2)
        f.flush(); os.fsync(f.fileno())


def read(path):
    return json.loads(Path(path).read_text(encoding='utf-8'))


def evidence(ref):
    raw = Path(ref['path']).read_bytes()
    if hashlib.sha256(raw).hexdigest() != ref['sha256']:
        raise ValueError('improvement_evidence_changed')
    return raw


class Journal:
    """New run only. Never silently resume/replay an interrupted external action."""
    def __init__(self, directory, run_id):
        self.directory = Path(directory)
        self.directory.mkdir(parents=True, exist_ok=False, mode=0o700)
        self.run_id, self.seq, self.previous = run_id, 0, None

    def emit(self, kind, payload):
        validate(kind, payload)
        value = dict(format='capability_improvement_event_v1', run_id=self.run_id,
                     sequence=self.seq, previous_sha256=self.previous, kind=kind, payload=payload)
        validate('event', value)
        with (self.directory/'events.jsonl').open('a', encoding='utf8') as f:
            os.chmod(f.name, 0o600)
            f.write(json.dumps(value, ensure_ascii=False, allow_nan=False)+'\n')
            f.flush(); os.fsync(f.fileno())
        self.previous = capability_digest(value)
        self.seq += 1


def discover(job):
    """Turn a host-authored task observation into an auditable bounded opportunity.

    Input adapters must extract observations from authorized training/validation
    traces. This layer does not infer economic benefits from repetition alone.
    """
    observations = job['observations']
    for item in observations:
        evidence(item['evidence'])
    for ref in job.get('source_evidence',[]):
        evidence(ref)
    relevant = [o for o in observations if o['split'] in ('training', 'validation')]
    if not relevant or len(relevant) != len(observations):
        action, reason = 'defer', 'heldout_or_missing_observation'
    elif job['objective'] == 'cost_reduction':
        assessment = job.get('optimization_assessment')
        if assessment is None:
            action, reason = 'defer', 'f02_assessment_required'
        else:
            from src.adapters.rsi_optimization import record
            payload = record(evidence(assessment), 'optimization_assessment')
            observed_tasks = {o['task_id'] for o in relevant}
            if not observed_tasks.intersection(payload['discovery_task_ids']):
                raise ValueError('improvement_assessment_task_mismatch')
            action = payload.get('action')
            if action not in ('start', 'defer', 'skip'):
                raise ValueError('improvement_assessment_invalid')
            reason = 'f02_' + action
    elif any(o['kind'] in ('task_failure', 'new_requirement', 'repeated_structure') for o in relevant):
        action, reason = 'start', 'bounded_capability_acquisition_trial'
    else:
        action, reason = 'defer', 'acquisition_need_missing'
    return dict(opportunity_id=job['id'], objective=job['objective'],
                observations=observations, action=action, reason=reason)


def repair_signature(result, outcome, attempt):
    """Same error at the same location on the same content is repetition.

    A changed signature only permits another attempt; it never proves progress.
    """
    observation = outcome or result
    diagnostics = result.get('diagnostics') or {}
    locations = [issue.get('path', []) for issue in diagnostics.get('issues', [])]
    if diagnostics.get('kind') == 'json_syntax':
        locations.append([diagnostics.get('line'), diagnostics.get('column')])
    if outcome:
        locations = [check.get('id') for check in (outcome.get('feedback') or {}).get('checks', [])
                     if check.get('status') != 'passed']
    candidate_sha = None
    for name in ('proposal.json', 'draft.json'):
        path = Path(attempt)/name
        if path.exists():
            candidate_sha = capability_digest(read(path))
            break
    if candidate_sha is None and (Path(attempt)/'answer.txt').exists():
        candidate_sha = hashlib.sha256((Path(attempt)/'answer.txt').read_bytes().strip()).hexdigest()
    return {'format':'capability_repair_signature_v1','error':observation.get('error','construction_failed'),
            'locations':locations,'candidate_sha256':candidate_sha}


def run_improvement(plan, adapter, *, execute=False):
    """Adapter methods: library(), construct(), publish(); production uses Source.

    The bounded queue combines host jobs and adapter-discovered opportunities.
    A repair keeps the task/catalog/snapshot frozen. A new opportunity refreshes
    the published library, so a newly certified C is available when building D.
    """
    validate('plan', plan)
    def verify_scene():
        for ref in ([plan['scene_adapter']] if plan.get('scene_adapter') else [])+plan.get('scene_dependencies',[]):evidence(ref)
        if plan.get('learning_routes'):evidence(plan['learning_routes'])
    verify_scene()
    if len({j['id'] for j in plan['jobs']}) != len(plan['jobs']):
        raise ValueError('improvement_duplicate_opportunity')
    # Check every task/evidence before any paid work. Frozen bytes are rechecked
    # at each use; changes fail closed, they never become repair feedback.
    for job in plan['jobs']:
        evidence(job['task'])
        discover(job)
    journal = Journal(plan['output'], plan['id'])
    save(journal.directory/'plan.json', plan)
    policy_sha = capability_digest(plan['policy'])
    save(journal.directory/'effective.json', dict(plan_sha256=capability_digest(plan),
        policy_sha256=policy_sha, execute=execute, code_sha256={name:hashlib.sha256((ROOT/name).read_bytes()).hexdigest()
        for name in ('src/adapters/capability_improvement.py','schemas/capability-improvement-v1.schema.json',
                     'src/adapters/capability_store.ts','src/adapters/capability_authoring.py','src/adapters/capability_feedback.py',
                     'src/adapters/capability_discovery.py','src/adapters/capability_scene.py',
                     'src/adapters/capability_cycle.ts','src/adapters/capability_proposal.py',
                     'src/adapters/capability_materials.py','src/adapters/capability_materials.ts',
                     'src/adapters/capability_trajectory.py','src/adapters/source_capability_runtime.ts',
                     'scenarios/remotion_edit/structured/capability_learning.py',
                     'scenarios/remotion_edit/structured/learn_programs.py',
                     'scenarios/remotion_edit/structured/certify_programs.py',
                     'scripts/export-capability-construction-library.mjs',
                     'scripts/complete-source-capability-loop.mjs',
                     'scenarios/remotion_edit/structured/run_capability_improvement.py',
                     'scenarios/remotion_edit/structured/capability_observations.py',
                     'scenarios/remotion_edit/structured/verify_capability_outputs.py')}))
    summary = dict(format='capability_improvement_result_v1', status='preview' if not execute else 'completed',
                   outcomes=[], efficiency_conclusion=None, creation_benefit=None)

    def decision(opportunity, action, reason, refs=()):
        journal.emit('decision', dict(opportunity_id=opportunity, action=action, reason=reason,
                     policy_sha256=policy_sha, evidence_refs=list(refs)))

    try:
        if execute and hasattr(adapter, 'freeze'):
            adapter.freeze(journal.directory)
        jobs=list(plan['jobs'])
        if plan.get('discovery') and not hasattr(adapter,'discover_jobs'):
            raise ValueError('improvement_discovery_adapter_required')
        if hasattr(adapter,'discover_jobs'):
            jobs.extend(adapter.discover_jobs(journal.directory))
        if not jobs and not plan.get('discovery'):
            raise ValueError('improvement_jobs_or_discovery_required')
        if len({job['id'] for job in jobs})!=len(jobs):raise ValueError('improvement_duplicate_opportunity')
        for job in jobs:
            validate('job',job);evidence(job['task']);discover(job)
        save(journal.directory/'resolved-jobs.json',jobs)
        waiting={}; rounds={}
        while jobs or waiting:
            if not jobs:
                # Only revisit a waiting opportunity when its currently usable
                # library changed. No timer, unchanged retry, or user-task replay.
                current=adapter.library()['snapshot']['digest']
                jobs=[j for j,seen in waiting.values() if seen!=current and adapter.admission(j)[0]=='start'] if hasattr(adapter,'admission') else []
                if not jobs:break
                for j in jobs:waiting.pop(j['id'])
            if hasattr(adapter,'prioritize_jobs'):jobs=adapter.prioritize_jobs(jobs)
            job=jobs.pop(0)
            opportunity = discover(job)
            if execute and opportunity['action']=='start' and hasattr(adapter,'admission'):
                action,reason=adapter.admission(job)
                if action=='defer' and reason=='construction_gap_requires_new_material_or_evidence' and plan.get('learning_routes') and hasattr(adapter,'pending_gap'):
                    pending=adapter.pending_gap(job)
                    if pending:
                        verify_scene()
                        for ref in job.get('source_evidence',[]):evidence(ref)
                        resumed=journal.directory/(job['id']+'-pending-gap');resumed.mkdir(mode=0o700)
                        save(resumed/'result.json',pending[0]);save(resumed/'original-gap.json',pending[1])
                        acquisition=adapter.acquire(job,pending[0],resumed)
                        save(resumed/'acquisition.json',acquisition)
                        if acquisition.get('status')=='registered':action,reason=adapter.admission(job)
                        else:reason=acquisition.get('reason',reason)
                if action!='start':opportunity.update(action=action,reason=reason)
            journal.emit('opportunity', opportunity)
            decision(job['id'], opportunity['action'], opportunity['reason'])
            if opportunity['action'] != 'start' or not execute:
                summary['outcomes'].append(dict(opportunity_id=job['id'], status=opportunity['action'] if execute else 'preview'))
                if execute and opportunity['action']=='defer':waiting[job['id']]=(job,adapter.library()['snapshot']['digest'])
                continue
            round_index=rounds.get(job['id'],0);rounds[job['id']]=round_index+1
            folder = journal.directory/(job['id'] if round_index==0 else job['id']+'-reevaluation-'+str(round_index)); folder.mkdir(mode=0o700)
            library = adapter.library()
            snapshot = validate_capability_snapshot(library['snapshot'], plan['owner'])
            if any(c['certification'] != 'certified' or c['lifecycle'] == 'archived' for c in snapshot['capabilities']):
                raise ValueError('improvement_library_not_certified')
            save(folder/'library.json', library)
            task = json.loads(evidence(job['task']))
            parent, feedback, failures, attempt_index, repairs = None, None, set(), 0, 0
            while True:
                # Independent checks and host context cannot change during repair.
                verify_scene()
                evidence(job['task'])
                for ref in job.get('source_evidence',[]):evidence(ref)
                attempt = folder/('attempt-'+str(attempt_index))
                attempt_id = folder.name+'/'+attempt.name
                journal.emit('attempt', dict(opportunity_id=job['id'], attempt_id=attempt_id,
                    parent_attempt_id=None if parent is None else folder.name+'/'+parent.name,
                    phase='started', snapshot_sha256=snapshot['digest'], visible=snapshot['roots'],
                    selected=[], result_ref=None, observed_model_usd=None))
                result = adapter.construct(task, library, attempt, parent, feedback)
                result_ref = {'path':str(attempt/'result.json'),
                              'sha256':hashlib.sha256((attempt/'result.json').read_bytes()).hexdigest()}
                selected, candidate = [], None
                if result['status'] == 'compiled_candidate':
                    candidate = read(attempt/'candidate.json')
                    if candidate['construction_snapshot_sha256'] != snapshot['digest']:
                        raise ValueError('improvement_construction_snapshot_changed')
                    selected = candidate['capability']['dependencies']
                journal.emit('attempt', dict(opportunity_id=job['id'], attempt_id=attempt_id,
                    parent_attempt_id=None if parent is None else folder.name+'/'+parent.name,
                    phase='compiled' if candidate else 'failed', snapshot_sha256=snapshot['digest'],
                    visible=snapshot['roots'], selected=selected, result_ref=result_ref,
                    observed_model_usd=result.get('observed_model_usd')))
                for ref in selected:
                    journal.emit('contribution', dict(opportunity_id=job['id'], attempt_id=attempt_id,
                        stage='construction', capability=ref, beneficiary=capability_ref(candidate['capability']),
                        observation='selected_in_compiled_proposal', quality='unverified',
                        evidence_ref=result_ref, observed_model_usd=None, benefit=None))
                outcome = None
                if candidate:
                    decision(job['id'], 'validate', 'compiled_candidate_requires_independent_check', [result_ref])
                    verify_scene()
                    for ref in job.get('source_evidence',[]):evidence(ref)
                    outcome = adapter.publish(job, candidate, attempt, library['head'])
                    publication_ref = outcome.get('evidence_ref')
                    if outcome['status'] == 'published':
                        if hasattr(adapter,'record_outcome'):adapter.record_outcome(job,attempt,result,candidate,outcome)
                        # Read the Store again; no candidate metadata promotion here.
                        refreshed = adapter.library()
                        new_ref = capability_ref(candidate['capability'])
                        if new_ref not in refreshed['snapshot']['roots']:
                            raise ValueError('improvement_published_root_not_visible')
                        save(attempt/'next-library.json', refreshed)
                        for ref in selected:
                            journal.emit('contribution', dict(opportunity_id=job['id'], attempt_id=attempt_id,
                                stage='construction', capability=ref, beneficiary=new_ref,
                                observation='contributed_to_validated_capability', quality='passed',
                                evidence_ref=publication_ref, observed_model_usd=None, benefit=None))
                            decision(job['id'], 'retain', 'validated_construction_use_even_without_direct_frequency', [publication_ref])
                        journal.emit('contribution', dict(opportunity_id=job['id'], attempt_id=attempt_id,
                            stage='execution', capability=new_ref, beneficiary=None,
                            observation='independent_followup_execution', quality='passed',
                            evidence_ref=publication_ref, observed_model_usd=None, benefit=None))
                        decision(job['id'], 'continue', 'published_capability_added_to_next_builder', [publication_ref])
                        summary['outcomes'].append(dict(opportunity_id=job['id'], status='published', capability=new_ref,
                                                       publication_sha256=outcome['publication_sha256']))
                        break
                    if outcome.get('committed'):
                        if hasattr(adapter,'record_outcome'):adapter.record_outcome(job,attempt,result,candidate,outcome)
                        # Publication succeeded but followup/reload failed. Never
                        # replay it as a model repair or silently reuse this result.
                        decision(job['id'], 'stop', 'committed_publication_requires_review', [publication_ref] if publication_ref else [])
                        summary['status'] = 'needs_review'
                        summary['outcomes'].append(dict(opportunity_id=job['id'], status='committed_followup_failed'))
                        save(journal.directory/'result.json', summary)
                        return summary
                if hasattr(adapter,'record_outcome'):adapter.record_outcome(job,attempt,result,candidate,outcome)
                if result.get('status')=='deferred' and hasattr(adapter,'acquire'):
                    verify_scene()
                    for ref in job.get('source_evidence',[]):evidence(ref)
                    acquisition=adapter.acquire(job,result,attempt)
                    save(attempt/'acquisition.json',acquisition)
                    acquisition_ref={'path':str(attempt/'acquisition.json'),
                        'sha256':hashlib.sha256((attempt/'acquisition.json').read_bytes()).hexdigest()}
                    if acquisition.get('status')=='registered':
                        refreshed=adapter.library()
                        next_snapshot=validate_capability_snapshot(refreshed['snapshot'],plan['owner'])
                        if any(c['certification']!='certified' or c['lifecycle']=='archived' for c in next_snapshot['capabilities']):
                            raise ValueError('improvement_library_not_certified')
                        # Re-evaluate before constructing again. A learner's
                        # success flag alone never wakes a user operation.
                        if next_snapshot['digest']!=snapshot['digest'] and adapter.admission(job)[0]=='start':
                            decision(job['id'],'continue','certified_material_registered_re_evaluate_opportunity',[acquisition_ref])
                            library,snapshot=refreshed,next_snapshot
                            save(attempt/'next-library.json',library)
                            parent,feedback,failures,repairs=None,None,set(),0
                            attempt_index+=1
                            continue
                    decision(job['id'],'defer',acquisition.get('reason','learning_did_not_change_available_material'),[acquisition_ref])
                reason = (outcome or result).get('error', 'construction_failed')
                signature = repair_signature(result, outcome, attempt)
                fingerprint = capability_digest(signature)
                save(attempt/'repair-signature.json', signature)
                max_repairs = plan['policy']['max_repairs']
                repairable = result.get('status')!='deferred' and (outcome is None or
                    outcome.get('repairable',reason=='capability_store_validation_failed') is True)
                retry = repairable and fingerprint not in failures and (max_repairs is None or repairs < max_repairs)
                decision(job['id'], 'repair' if retry else 'defer',
                         'new_failure_feedback' if retry else 'construction_gap_requires_new_material_or_evidence' if result.get('status')=='deferred'
                         else 'infrastructure_repeated_failure_or_explicit_repair_limit', [result_ref])
                if not retry:
                    summary['outcomes'].append(dict(opportunity_id=job['id'], status='deferred', error=reason))
                    waiting[job['id']]=(job,snapshot['digest'])
                    break
                failures.add(fingerprint)
                feedback = dict(error=reason, diagnostics=result.get('diagnostics'),
                                repeat_signature=signature, progress='not_established',
                                validation=outcome.get('feedback') if outcome else None,
                                source_attempt_id=attempt_id, scope='training_or_validation')
                parent, attempt_index = attempt, attempt_index+1
                repairs+=1
    except BaseException as error:
        summary['status'] = 'interrupted' if isinstance(error, (KeyboardInterrupt, SystemExit)) else 'failed'
        summary['error'] = str(error)
        save(journal.directory/'result.json', summary)
        raise
    save(journal.directory/'result.json', summary)
    return summary
