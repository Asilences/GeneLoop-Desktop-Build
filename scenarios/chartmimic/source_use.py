"""Declare future training use of a closed Reuse-side task, preserving history."""
import hashlib
import json
from pathlib import Path
import re


def reference(path):
    path = Path(path).resolve()
    return {'path': str(path), 'sha256': hashlib.sha256(path.read_bytes()).hexdigest()}


def checked(reference):
    path = Path(reference['path']).resolve()
    raw = path.read_bytes()
    if hashlib.sha256(raw).hexdigest() != reference['sha256']:
        raise ValueError('chartmimic_retirement_evidence_changed')
    return json.loads(raw)


def retired_source(trial, generation, evidence):
    """A source-use decision is distinct from the original task's frozen role."""
    trial = Path(trial).resolve()
    if (not isinstance(generation, str)
            or not re.fullmatch('[a-z0-9][a-z0-9_-]{0,95}', generation)
            or evidence is None):
        raise ValueError('chartmimic_explicit_future_generation_and_retirement_required')
    effective_ref = reference(trial / 'effective.json')
    result_ref = reference(trial / 'result.json')
    effective, result = checked(effective_ref), checked(result_ref)
    if (effective['role'] != 'successor' or effective.get('mode') != 'successor_reuse'
            or result['status'] != 'completed'):
        raise ValueError('chartmimic_completed_reuse_side_source_required')
    evidence_ref = reference(evidence)
    report = checked(evidence_ref)
    if (report.get('task_id') != effective['task_id'] or report.get('generation_id') == generation
            or report.get('evaluation_complete') is not True
            or report.get('training_source_eligible') is not True):
        raise ValueError('chartmimic_closed_evaluated_source_required')
    arms = report.get('arms', {})
    if (set(arms) != {'reuse', 'baseline'} or arms['reuse'].get('result') != result_ref
            or arms['reuse'].get('effective') != effective_ref):
        raise ValueError('chartmimic_retirement_source_mismatch')
    for name, arm in arms.items():
        record, settings = checked(arm['result']), checked(arm['effective'])
        if (settings['task_id'] != effective['task_id']
                or record.get('status') not in ('completed', 'failed', 'incomplete')):
            raise ValueError('chartmimic_pair_not_closed')
        expected = 'successor_reuse' if name == 'reuse' else 'baseline'
        if settings.get('mode') != expected:
            raise ValueError('chartmimic_paired_source_mode_invalid')
        for evaluation in arm.get('evaluations', []):
            checked(evaluation)
    return {'original_role': effective['role'], 'next_generation': generation,
        'source_result': result_ref, 'source_effective': effective_ref, 'retirement_evidence': evidence_ref,
        'decision_code': reference(__file__),
        'scope': 'future_learning_from_retired_normal_Reuse_experience; original_trial_and_scores_unchanged'}
