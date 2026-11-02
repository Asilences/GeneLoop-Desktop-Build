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
SCHEMA = json.loads((ROOT/'schemas/capability-improvement-v1.schema.json').read_text())


def validate(kind, value):
    Draft202012Validator({'$ref': '#/$defs/'+kind, '$defs': SCHEMA['$defs']}).validate(value)
    return value


def save(path, value):
    with Path(path).open('x', encoding='utf8') as f:
        os.chmod(path, 0o600)
        json.dump(value, f, ensure_ascii=False, allow_nan=False, indent=2)
        f.flush(); os.fsync(f.fileno())


def read(path):
    return json.loads(Path(path).read_text())


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
    elif any(o['kind'] in ('task_failure', 'new_requirement') for o in relevant):
        action, reason = 'start', 'bounded_capability_acquisition_trial'
    else:
        action, reason = 'defer', 'acquisition_need_missing'
    return dict(opportunity_id=job['id'], objective=job['objective'],
                observations=observations, action=action, reason=reason)


def run_improvement(plan, adapter, *, execute=False):
    """Adapter methods: library(), construct(), publish(); production uses Source.

    The bounded job queue is host supplied; model chooses capability composition.
    A repair keeps the task/catalog/snapshot frozen. A new opportunity refreshes
    the published library, so a newly certified C is available when building D.
    """
    validate('plan', plan)
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
                     'src/adapters/capability_store.ts','scripts/export-capability-construction-library.mjs',
                     'scripts/complete-source-capability-loop.mjs',
                     'scenarios/remotion_edit/structured/run_capability_improvement.py',
                     'scenarios/remotion_edit/structured/verify_capability_outputs.py')}))
    summary = dict(format='capability_improvement_result_v1', status='preview' if not execute else 'completed',
                   outcomes=[], efficiency_conclusion=None, creation_benefit=None)

    def decision(opportunity, action, reason, refs=()):
        journal.emit('decision', dict(opportunity_id=opportunity, action=action, reason=reason,
                     policy_sha256=policy_sha, evidence_refs=list(refs)))

    try:
        if execute and hasattr(adapter, 'freeze'):
            adapter.freeze(journal.directory)
        for job in plan['jobs']:
            opportunity = discover(job)
            journal.emit('opportunity', opportunity)
            decision(job['id'], opportunity['action'], opportunity['reason'])
            if opportunity['action'] != 'start' or not execute:
                summary['outcomes'].append(dict(opportunity_id=job['id'], status=opportunity['action'] if execute else 'preview'))
                continue
            folder = journal.directory/job['id']; folder.mkdir(mode=0o700)
            library = adapter.library()
            snapshot = validate_capability_snapshot(library['snapshot'], plan['owner'])
            if any(c['certification'] != 'certified' or c['lifecycle'] == 'archived' for c in snapshot['capabilities']):
                raise ValueError('improvement_library_not_certified')
            save(folder/'library.json', library)
            task = json.loads(evidence(job['task']))
            parent, feedback, failures, attempt_index = None, None, set(), 0
            while True:
                # Independent checks and host context cannot change during repair.
                evidence(job['task'])
                attempt = folder/('attempt-'+str(attempt_index))
                attempt_id = job['id']+'/'+attempt.name
                journal.emit('attempt', dict(opportunity_id=job['id'], attempt_id=attempt_id,
                    parent_attempt_id=None if parent is None else job['id']+'/'+parent.name,
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
                    parent_attempt_id=None if parent is None else job['id']+'/'+parent.name,
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
                    outcome = adapter.publish(job, candidate, attempt, library['head'])
                    publication_ref = outcome.get('evidence_ref')
                    if outcome['status'] == 'published':
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
                        # Publication succeeded but followup/reload failed. Never
                        # replay it as a model repair or silently reuse this result.
                        decision(job['id'], 'stop', 'committed_publication_requires_review', [publication_ref] if publication_ref else [])
                        summary['status'] = 'needs_review'
                        summary['outcomes'].append(dict(opportunity_id=job['id'], status='committed_followup_failed'))
                        save(journal.directory/'result.json', summary)
                        return summary
                reason = (outcome or result).get('error', 'construction_failed')
                fingerprint = capability_digest(reason)
                max_repairs = plan['policy']['max_repairs']
                repairable = outcome is None or reason in ('loop_independent_validation_failed',
                    'capability_store_validation_failed','loop_video_result_missing')
                retry = repairable and fingerprint not in failures and (max_repairs is None or attempt_index < max_repairs)
                decision(job['id'], 'repair' if retry else 'defer',
                         'new_failure_feedback' if retry else 'infrastructure_repeated_failure_or_explicit_repair_limit', [result_ref])
                if not retry:
                    summary['outcomes'].append(dict(opportunity_id=job['id'], status='deferred', error=reason))
                    break
                failures.add(fingerprint)
                feedback = dict(error=reason, validation=outcome.get('feedback') if outcome else None,
                                source_attempt_id=attempt_id, scope='training_or_validation')
                parent, attempt_index = attempt, attempt_index+1
    except BaseException as error:
        summary['status'] = 'interrupted' if isinstance(error, (KeyboardInterrupt, SystemExit)) else 'failed'
        summary['error'] = str(error)
        save(journal.directory/'result.json', summary)
        raise
    save(journal.directory/'result.json', summary)
    return summary
