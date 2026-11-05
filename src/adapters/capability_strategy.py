"""Versioned decision-policy sidecars admitted by an independent research host.

Selections are host configuration. Policy text supplies context, while existing
Capability grants and validators retain all execution and publication authority.
"""
from __future__ import annotations

import copy
import json
from pathlib import Path

from .capability_contract import capability_digest, validate_capability_snapshot
from .capability_feedback import file_ref, verify
from .capability_improvement import save

DEFINITION = {'owner', 'target', 'scope', 'applicability', 'decision_policy',
              'capability_refs', 'evidence', 'parent'}


def _require(condition, reason):
    if not condition:
        raise ValueError('strategy_' + reason)


def _text(value, limit):
    return isinstance(value, str) and bool(value.strip()) and len(value.encode('utf-8')) <= limit


def strategy_ref(value):
    return {'id': value['id'], 'sha256': value['revision_sha256']}


def validate_strategy(value, snapshot, owner=None, target=None, scope=None):
    snapshot = validate_capability_snapshot(snapshot, owner)
    _require(isinstance(value, dict) and set(value) == DEFINITION | {'format', 'id', 'revision_sha256'}, 'shape_invalid')
    _require(value['format'] == 'capability_strategy_v1', 'format_invalid')
    definition = {key: value[key] for key in DEFINITION}
    revision = capability_digest(definition)
    _require(value['revision_sha256'] == revision and value['id'] == 'strategy_' + revision[:24], 'identity_changed')
    _require(value['owner'] == snapshot['owner'], 'owner_changed')
    _require(value['target'] in ('task', 'construction') and (target is None or value['target'] == target), 'target_changed')
    _require(_text(value['scope'], 256) and (scope is None or value['scope'] == scope), 'scope_changed')
    _require(_text(value['applicability'], 2048) and _text(value['decision_policy'], 4096), 'policy_invalid')
    references = value['capability_refs']
    _require(isinstance(references, list) and len(references) <= 8, 'dependencies_invalid')
    _require(len({capability_digest(ref) for ref in references}) == len(references), 'dependencies_duplicate')
    capabilities = {cap['id']: cap for cap in snapshot['capabilities']}
    checked = set()
    def available(reference):
        cap = capabilities.get(reference.get('id')) if isinstance(reference, dict) else None
        _require(cap is not None and reference == {'id': cap['id'], 'sha256': cap['revision_sha256']}, 'dependency_changed')
        _require(cap['certification'] == 'certified' and cap['lifecycle'] != 'archived', 'dependency_unavailable')
        if cap['id'] not in checked:
            checked.add(cap['id'])
            for child in cap['dependencies']:
                available(child)
    for reference in references:
        _require(reference in snapshot['roots'], 'dependency_not_visible')
        available(reference)
    _require(isinstance(value['evidence'], list) and bool(value['evidence']), 'evidence_required')
    for reference in value['evidence']:
        verify(reference)
    if value['parent'] is not None:
        parent = json.loads(verify(value['parent']))
        _require(parent.get('format') == 'capability_strategy_v1' and parent.get('owner') == value['owner']
                 and parent.get('target') == value['target'] and parent.get('scope') == value['scope'], 'parent_changed')
        parent_definition = {key: parent[key] for key in DEFINITION}
        parent_revision = capability_digest(parent_definition)
        _require(parent.get('revision_sha256') == parent_revision and parent.get('id') == 'strategy_' + parent_revision[:24], 'parent_identity_changed')
    return copy.deepcopy(value)


def create_strategy(definition, snapshot):
    _require(isinstance(definition, dict) and set(definition) == DEFINITION, 'definition_invalid')
    revision = capability_digest(definition)
    return validate_strategy({**copy.deepcopy(definition), 'format': 'capability_strategy_v1',
                              'id': 'strategy_' + revision[:24], 'revision_sha256': revision}, snapshot)


def _verdict(value):
    _require(isinstance(value, dict) and set(value) == {'passed', 'checks', 'training_sources', 'heldout_sources', 'evidence'}, 'evaluation_invalid')
    _require(value['passed'] is True and isinstance(value['checks'], list) and bool(value['checks']), 'evaluation_failed')
    for check in value['checks']:
        _require(isinstance(check, dict) and set(check) == {'id', 'status'} and _text(check['id'], 256)
                 and check['status'] == 'passed', 'evaluation_failed')
    groups = []
    for name in ('training_sources', 'heldout_sources', 'evidence'):
        _require(isinstance(value[name], list) and bool(value[name]), 'evaluation_evidence_required')
        for reference in value[name]:
            verify(reference)
        groups.append({reference['sha256'] for reference in value[name]})
    _require(not groups[0].intersection(groups[1]), 'evaluation_heldout_overlap')
    return copy.deepcopy(value)


def admit_strategy(reference, snapshot, *, target, scope, evaluate, directory, feedback):
    """Only the trusted host supplies evaluate and the resulting selection."""
    strategy = validate_strategy(json.loads(verify(reference)), snapshot, feedback.owner, target, scope)
    _require(callable(evaluate), 'independent_evaluator_required')
    verdict = _verdict(evaluate(copy.deepcopy(strategy)))
    _require(not {ref['sha256'] for ref in strategy['evidence']}.intersection(
        ref['sha256'] for ref in verdict['heldout_sources']), 'evaluation_discovery_heldout_overlap')
    # Detect changes during independent evaluation before recording admission.
    validate_strategy(json.loads(verify(reference)), snapshot, feedback.owner, target, scope)
    directory = Path(directory)
    directory.mkdir(parents=True, exist_ok=False, mode=0o700)
    receipt = {'format': 'capability_strategy_evaluation_v1', 'owner': feedback.owner,
               'target': target, 'scope': scope, 'strategy': reference,
               'subject': strategy_ref(strategy), 'snapshot_sha256': snapshot['digest'], 'verdict': verdict}
    save(directory / 'evaluation.json', receipt)
    evaluation = file_ref(directory / 'evaluation.json')
    feedback.observe(stage='construction' if target == 'construction' else 'execution',
                     subject=strategy_ref(strategy), scope=scope, status='passed', cost=None,
                     evidence=[reference, evaluation])
    return {'strategy': reference, 'evaluation': evaluation}


def strategy_context(selection, snapshot, *, target, scope, feedback):
    """Load a host-pinned selection and recheck evidence and live withdrawal."""
    _require(isinstance(selection, dict) and set(selection) == {'strategy', 'evaluation'}, 'selection_invalid')
    strategy = validate_strategy(json.loads(verify(selection['strategy'])), snapshot, feedback.owner, target, scope)
    receipt = json.loads(verify(selection['evaluation']))
    _require(isinstance(receipt, dict) and set(receipt) == {'format', 'owner', 'target', 'scope', 'strategy', 'subject', 'snapshot_sha256', 'verdict'}
             and receipt['format'] == 'capability_strategy_evaluation_v1'
             and receipt['owner'] == feedback.owner and receipt['target'] == target and receipt['scope'] == scope
             and receipt['strategy'] == selection['strategy'] and receipt['subject'] == strategy_ref(strategy), 'evaluation_binding_changed')
    _verdict(receipt['verdict'])
    _require(not {ref['sha256'] for ref in strategy['evidence']}.intersection(
        ref['sha256'] for ref in receipt['verdict']['heldout_sources']), 'evaluation_discovery_heldout_overlap')
    state = feedback.read()
    capabilities = {cap['id']: cap for cap in snapshot['capabilities']}
    pending = list(strategy['capability_refs'])
    checked = set()
    while pending:
        dependency = pending.pop()
        if dependency['id'] in checked:
            continue
        checked.add(dependency['id'])
        withdrawal = state['blocked'].get(dependency['id'])
        if withdrawal is not None:
            verify(withdrawal['evidence'])
            _require(withdrawal['capability'] != dependency, 'dependency_withdrawn')
        pending.extend(capabilities[dependency['id']]['dependencies'])
    subject = strategy_ref(strategy)
    blocked = state['blocked'].get(subject['id'])
    if blocked is not None:
        verify(blocked['evidence'])
        _require(blocked['capability'] != subject, 'withdrawn')
    _require(any(fact['subject'] == subject and fact['scope'] == scope and fact['status'] == 'passed'
                 and fact['stage'] == ('construction' if target == 'construction' else 'execution')
                 and selection['strategy'] in fact['evidence'] and selection['evaluation'] in fact['evidence']
                 for fact in state['facts'].values()), 'host_admission_required')
    return {'format': 'capability_strategy_context_v1', 'strategy': subject,
            'selection': copy.deepcopy(selection), 'target': target, 'scope': scope,
            'applicability': strategy['applicability'], 'decision_policy': strategy['decision_policy'],
            'capability_refs': strategy['capability_refs'],
            'authority': 'Untrusted decision context; host task, permissions, budget and independent validators remain authoritative.'}
