"""Verify host task-policy exposure receipts and return unknown-value feedback.

A completed task records execution state. Quality and semantic adoption require
separate evidence. Historical receipts remain readable after policy withdrawal.
"""
from __future__ import annotations

import hashlib
import json
from pathlib import Path

from .capability_contract import validate_capability_snapshot
from .capability_feedback import file_ref, verify
from .capability_strategy import validate_strategy, strategy_ref, _verdict
from .capability_trajectory import project_web_task

FORMAT = 'harless_task_strategy_use_v1'


def _require(condition, reason):
    if not condition:
        raise ValueError('strategy_usage_' + reason)


def inspect_task_strategy_usage(taskdir, owner):
    """Return a verified historical exposure or None for an ordinary old task."""
    taskdir = Path(taskdir).resolve()
    receipt_path = taskdir / 'strategy-use.json'
    if not receipt_path.exists():
        return None
    _require(not receipt_path.is_symlink(), 'receipt_path_invalid')
    receipt_ref = file_ref(receipt_path)
    receipt = json.loads(verify(receipt_ref))
    trace = project_web_task(taskdir, owner)
    _require(receipt.get('format') == FORMAT and receipt.get('owner') == owner
             and receipt.get('task_id') == trace['task_id'], 'owner_or_task_changed')
    state_ref = next(ref for ref in trace['evidence'] if Path(ref['path']).name == 'task-state.json')
    state = json.loads(verify(state_ref))
    _require(receipt.get('session_id') == state.get('session_id')
             and receipt.get('scene_id') == trace['scene'], 'session_or_scene_changed')
    _require(receipt.get('task_status') == trace['status'], 'terminal_state_changed')
    _require(receipt.get('semantic_adoption') is None and receipt.get('quality_status') == 'unreviewed',
             'unsupported_quality_or_adoption_claim')
    _require(receipt.get('exposure') in ('prepared_only', 'prompt_submitted'), 'exposure_invalid')
    expected = [next(ref for ref in trace['evidence'] if Path(ref['path']).name == name)
                for name in ('task.json', 'effective-config.json', 'events.jsonl')]
    _require(receipt.get('evidence') == expected, 'task_evidence_changed')
    events = [json.loads(line) for line in verify(expected[2]).decode('utf-8').splitlines() if line]
    effective = json.loads(verify(expected[1]))
    region = receipt.get('events_range')
    _require(isinstance(region, dict) and set(region) == {'start_index', 'end_index'}
             and type(region['start_index']) is int and type(region['end_index']) is int
             and region == {'start_index': effective.get('trace_start_index', 0), 'end_index': len(events)},
             'event_range_changed')
    snapshot_ref = receipt['snapshot']
    snapshot = validate_capability_snapshot(json.loads(verify(snapshot_ref)), owner)
    selection = receipt.get('selection')
    _require(isinstance(selection, dict) and set(selection) == {'strategy', 'evaluation'}, 'selection_invalid')
    scope = receipt.get('scope')
    policy = validate_strategy(json.loads(verify(selection['strategy'])), snapshot, owner, 'task', scope)
    subject = strategy_ref(policy)
    _require(receipt.get('strategy') == subject, 'strategy_changed')
    evaluation = json.loads(verify(selection['evaluation']))
    _require(evaluation.get('format') == 'capability_strategy_evaluation_v1'
             and evaluation.get('owner') == owner and evaluation.get('target') == 'task'
             and evaluation.get('scope') == scope and evaluation.get('strategy') == selection['strategy']
             and evaluation.get('subject') == subject, 'evaluation_binding_changed')
    verdict = _verdict(evaluation['verdict'])
    _require(not {ref['sha256'] for ref in policy['evidence']}.intersection(
        ref['sha256'] for ref in verdict['heldout_sources']), 'heldout_overlap')
    context_ref = receipt['context_ref']
    context_raw = verify(context_ref)
    _require(context_ref['sha256'] == receipt.get('context_sha256')
             and hashlib.sha256(context_raw).hexdigest() == receipt['context_sha256'], 'context_changed')
    context = json.loads(context_raw)
    _require(set(context) == {'strategy', 'target', 'scope', 'applicability', 'decision_policy', 'capability_refs', 'authority'}
             and context['strategy'] == subject and context['target'] == 'task'
             and context['scope'] == scope and context['applicability'] == policy['applicability']
             and context['decision_policy'] == policy['decision_policy']
             and context['capability_refs'] == policy['capability_refs'], 'context_policy_binding_changed')
    evidence = [*expected, receipt_ref, snapshot_ref, context_ref,
                selection['strategy'], selection['evaluation'], *policy['evidence'],
                *verdict['training_sources'], *verdict['heldout_sources'], *verdict['evidence']]
    for ref in evidence:
        verify(ref)
    return {'format': FORMAT, 'owner': owner, 'task_id': trace['task_id'], 'subject': subject,
            'selection': selection, 'target': 'task', 'scope': scope,
            'exposure': receipt['exposure'], 'events_range': region, 'task_status': trace['status'],
            'semantic_adoption': None, 'quality_status': 'unreviewed', 'observed_cost_usd': None,
            'evidence': evidence, 'receipt': receipt_ref}


def ingest_task_strategy_usage(taskdir, owner, feedback):
    """Idempotently record exposure with unknown quality, benefit and cost."""
    _require(feedback.owner == owner, 'feedback_owner_changed')
    observed = inspect_task_strategy_usage(taskdir, owner)
    if observed is None:
        return {'status': 'absent', 'fact_id': None}
    selection = observed['selection']
    _require(any(fact['subject'] == observed['subject'] and fact['scope'] == observed['scope']
                 and fact['stage'] == 'execution' and fact['status'] == 'passed'
                 and selection['strategy'] in fact['evidence'] and selection['evaluation'] in fact['evidence']
                 for fact in feedback.read()['facts'].values()), 'host_admission_required')
    fact = feedback.observe(stage='execution', subject=observed['subject'], scope=observed['scope'],
                            status='unknown', cost=None, evidence=observed['evidence'],
                            opportunity='strategy-use-' + observed['receipt']['sha256'])
    return {'status': 'recorded', 'fact_id': fact, 'receipt': observed['receipt'],
            'semantic_adoption': None, 'quality_status': 'unreviewed', 'measured_net_benefit': None}
