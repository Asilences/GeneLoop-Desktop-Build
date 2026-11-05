"""Thin shared orchestration over the existing investigation and receivers.

Scenes provide evidence inspectors, actual receivers and evaluation callbacks.
This module owns neither task scoring nor a separate model/learning loop.
"""
from __future__ import annotations

from pathlib import Path
import copy
import json

from .capability_evolution_investigation import run_investigation
from .capability_feedback import file_ref, verify
from .capability_improvement import save


def accumulate_evolution_feedback(investigation, result, *, output, feedback,
                                   investigation_result, supported_receivers=(), current_capabilities=None):
    """Finish or recover feedback from a verified original investigation.

    This stage performs no model calls or task evaluations. Recovery uses a new
    output directory and retains the original decision and source evidence.
    """
    stored = json.loads(verify(investigation_result))
    if (result.get('status') != stored.get('status') or
            result.get('investigation_identity') != stored.get('investigation_identity')):
        raise ValueError('evolution_cycle_original_decision_changed')
    fields = {'result', 'entries', 'history', 'inspector', 'snapshot', 'expose_evaluation'}
    if (not isinstance(feedback, dict) or set(feedback) - fields
            or not isinstance(feedback.get('result', {}), dict)
            or {'status', 'submissions', 'investigation_identity'}.intersection(feedback.get('result', {}))):
        raise ValueError('evolution_cycle_feedback_invalid')
    if current_capabilities is not None and 'snapshot' in feedback:
        raise ValueError('evolution_cycle_snapshot_source_ambiguous')
    directory = Path(output)
    directory.mkdir(parents=True, mode=0o700, exist_ok=True)
    if (directory / 'result.json').exists() or (directory / 'next-investigation-input').exists():
        raise ValueError('evolution_cycle_feedback_output_already_used')
    result = copy.deepcopy(result)
    result.update(feedback.get('result', {}))
    result['supported_receivers'] = sorted(supported_receivers)
    entries = feedback.get('entries', [])
    decision_path = directory / 'decision-feedback.json'
    save(decision_path, {'format': 'evolution_investigation_decision_v1',
        'owner': investigation.snapshot['owner'], 'status': result['status'],
        'investigation': investigation_result, 'production_default_changed': False})
    snapshot = current_capabilities if current_capabilities is not None else feedback.get('snapshot')
    next_view = investigation.continue_with(directory / 'next-investigation-input',
        entries=entries, inspector=feedback.get('inspector'), snapshot=snapshot,
        history=[file_ref(decision_path), *feedback.get('history', [])],
        expose_evaluation=feedback.get('expose_evaluation', False))
    next_view._index_evidence([investigation_result])
    save(directory / 'feedback-overview.json', next_view.overview())
    result['feedback_requery'] = {'status': 'queryable', 'observations': len(entries),
        'total_observations': len(next_view.observations), 'snapshot_sha256': next_view.snapshot['digest'],
        'decision': file_ref(decision_path), 'overview': file_ref(directory / 'feedback-overview.json')}
    save(directory / 'result.json', result)
    return result, next_view


def run_evolution_cycle(investigation, *, call_agent, handlers, output, limits,
                        followup_evaluator=None, load_current_capabilities=None, prior_results=()):
    allowed = {'max_tool_calls', 'timeout_seconds', 'local_only', 'require_no_change_evidence'}
    if (not isinstance(limits, dict) or set(limits) - allowed
            or not {'max_tool_calls', 'timeout_seconds'}.issubset(limits)
            or limits['max_tool_calls'] is None or limits['timeout_seconds'] is None):
        raise ValueError('evolution_cycle_finite_limits_required')
    if followup_evaluator is not None and not callable(followup_evaluator):
        raise ValueError('evolution_cycle_followup_callback_invalid')
    directory = Path(output)
    directory.mkdir(parents=True, mode=0o700, exist_ok=True)
    if (directory / 'result.json').exists() or (directory / 'agent').exists():
        raise ValueError('evolution_cycle_output_already_used')
    result = run_investigation(investigation, call_agent=call_agent, handlers=handlers,
        output=directory / 'agent', prior_results=prior_results, **limits)
    try:
        feedback = followup_evaluator(result) if followup_evaluator else {}
        return accumulate_evolution_feedback(investigation, result, output=directory, feedback=feedback,
            investigation_result=file_ref(directory / 'agent/result.json'), supported_receivers=handlers,
            current_capabilities=load_current_capabilities() if load_current_capabilities is not None else None)
    except BaseException as error:
        save(directory / 'cycle-error.json', {'status': 'interrupted' if isinstance(error, KeyboardInterrupt) else 'failed',
            'phase': 'followup_or_feedback', 'investigation': file_ref(directory / 'agent/result.json'),
            'error': type(error).__name__ + ':' + str(error)})
        raise
