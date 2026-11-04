"""Feedback-conditioned boundaries for the existing Capability/Motif learner.

Host feedback and a proposed region are evidence to explore, not a certificate.
This module neither publishes a capability nor owns budgets, models or a loop.
All old versions and rejected candidates remain available in their old stores.
"""
from __future__ import annotations

import copy
import json
from pathlib import Path

from .capability_contract import capability_digest, capability_ref, validate_capability_snapshot
from .capability_feedback import file_ref, verify
from .capability_improvement import save


def value_context(feedback, subject, scope):
    """Keep evidence of execution and creation separate; never issue credit."""
    state = feedback.read()
    facts = {key: copy.deepcopy(value) for key, value in state['facts'].items()
             if value['scope'] == scope and
             (value['subject'] == subject or value.get('beneficiary') == subject)}
    return {'owner': feedback.owner, 'scope': scope, 'subject': copy.deepcopy(subject),
            'execution': {key: row for key, row in facts.items() if row['stage'] == 'execution'},
            'creation': {key: row for key, row in facts.items() if row['stage'] == 'construction'},
            'attempts': {key: row for key, row in facts.items() if row['stage'] == 'attempt'},
            'budget_credit': None, 'total_economic_benefit': None}


def propose_evolution_boundary(training, *, feedback, prior_candidate, scope,
                               proposer, directory, enabled=False):
    """One proposal through the host's existing Builder; heldout is never sent.

    The callback receives actual separate value evidence and training graphs.
    It may abstain or return feedback_ids and observed training regions. The
    host independently supplies matching heldout regions before compilation.
    No fixed shrink/expand direction or model call is built into this adapter.
    """
    if not enabled:
        return {'status': 'disabled', 'proposal': None}
    previous = json.loads(verify(prior_candidate))
    previous = previous.get('compiled', previous)
    cap = previous.get('capability', previous)
    if cap['owner'] != feedback.owner:
        raise ValueError('evolution_prior_binding_changed')
    subject = capability_ref(cap)
    context = value_context(feedback, subject, scope)
    from .capability_motif_learning import _checked
    traces = [_checked(trace, feedback.owner) for trace in training]
    request = {'subject': subject, 'scope': scope, 'prior': copy.deepcopy(cap),
               'values': context, 'training': traces,
               'authority': 'candidate boundaries only; original independent verification remains required'}
    directory = Path(directory)
    directory.mkdir(parents=True, mode=0o700, exist_ok=False)
    save(directory / 'request.json', request)
    try:
        response = proposer(copy.deepcopy(request))
        save(directory / 'response.json', response)
        verify(prior_candidate)
        if value_context(feedback, subject, scope) != context:
            raise ValueError('evolution_feedback_changed')
        if response is None:
            result = {'status': 'deferred', 'proposal': None}
        else:
            if (not isinstance(response, dict) or set(response) != {'feedback_ids', 'regions'}
                    or not isinstance(response['regions'], dict)
                    or set(response['regions']) != {trace['task_id'] for trace in traces}):
                raise ValueError('evolution_training_proposal_invalid')
            facts = {**context['execution'], **context['creation'], **context['attempts']}
            if not response['feedback_ids'] or any(key not in facts for key in response['feedback_ids']):
                raise ValueError('evolution_relevant_feedback_required')
            result = {'status': 'proposed', 'proposal': {'subject': subject, 'scope': scope, **response}}
        result['request_evidence'] = file_ref(directory / 'request.json')
        result['response_evidence'] = file_ref(directory / 'response.json')
        save(directory / 'result.json', result)
        return result
    except BaseException as error:
        save(directory / 'failure.json', {
            'status': 'interrupted' if isinstance(error, (KeyboardInterrupt, SystemExit)) else 'failed',
            'error': type(error).__name__ + ':' + str(error)})
        raise


def validate_evolution_request(training, heldout, snapshot, *, feedback, prior_candidate, proposal):
    """Read-only preflight shared by preview and actual candidate learning."""
    snapshot = validate_capability_snapshot(snapshot, feedback.owner)
    previous = json.loads(verify(prior_candidate))
    previous = previous.get('compiled', previous)
    cap = previous.get('capability', previous)
    prior_ref = capability_ref(cap)
    if cap['owner'] != feedback.owner or proposal.get('subject') != prior_ref:
        raise ValueError('evolution_prior_binding_changed')
    if set(proposal) != {'subject', 'scope', 'feedback_ids', 'regions'}:
        raise ValueError('evolution_proposal_fields_invalid')
    context = value_context(feedback, prior_ref, proposal['scope'])
    available = {**context['execution'], **context['creation'], **context['attempts']}
    ids = proposal['feedback_ids']
    if not isinstance(ids, list) or not ids or len(set(ids)) != len(ids) or any(i not in available for i in ids):
        raise ValueError('evolution_relevant_feedback_required')
    traces = [*training, *heldout]
    trace_ids = [t['task_id'] for t in traces]
    if len(set(trace_ids)) != len(trace_ids) or set(proposal['regions']) != set(trace_ids):
        raise ValueError('evolution_region_inventory_changed')
    for trace in traces:
        region = proposal['regions'][trace['task_id']]
        calls = [step['call_id'] for step in trace['steps']]
        if (not isinstance(region, list) or not region or len(set(region)) != len(region)
                or any(call not in calls for call in region)):
            raise ValueError('evolution_region_not_observed')
        positions = [calls.index(call) for call in region]
        if positions != list(range(positions[0], positions[-1] + 1)):
            raise ValueError('evolution_region_must_be_ordered_contiguous')
    return {'snapshot': snapshot, 'capability': cap, 'context': context}


def evolve_abstraction(training, heldout, snapshot, *, feedback, prior_candidate,
                       proposal, directory, enabled=False):
    """Compile different executable boundaries using the same original miner.

    `proposal` is a host/model candidate: {subject, scope, feedback_ids, regions}.
    `regions` maps each actual training/heldout task_id to its observed call_ids.
    The miner still decides which repeated patterns are supported; this function
    does not manufacture a D graph or promote a proposed capability to active.
    Heldout regions may only come from the trusted host, never a model prompt.
    """
    if not enabled:
        return {'status': 'disabled', 'candidates': [], 'rejected': [],
                'budget_credit': None, 'measured_improvement': None}
    checked = validate_evolution_request(training, heldout, snapshot, feedback=feedback,
                                         prior_candidate=prior_candidate, proposal=proposal)
    snapshot, cap, context = checked['snapshot'], checked['capability'], checked['context']
    prior_ref, ids = capability_ref(cap), proposal['feedback_ids']
    directory = Path(directory)
    directory.mkdir(parents=True, mode=0o700, exist_ok=False)
    save(directory / 'proposal.json', proposal)
    save(directory / 'feedback.json', context)
    save(directory / 'prior.json', {'candidate': prior_candidate, 'capability': prior_ref})
    try:
        # This is exactly the graph learning entry used by ordinary task traces.
        from .capability_motif_learning import learn_capability_motifs
        learned = learn_capability_motifs(training, heldout, snapshot, regions=proposal['regions'])
        verify(prior_candidate)
        # Feedback must not change while candidates are being constructed.
        if value_context(feedback, prior_ref, proposal['scope']) != context:
            raise ValueError('evolution_feedback_changed')
        result = {**learned, 'status': 'proposed', 'candidates': [],
                  'subject': prior_ref, 'feedback_ids': ids,
                  'feedback_evidence': file_ref(directory / 'feedback.json'),
                  'proposal_evidence': file_ref(directory / 'proposal.json'),
                  'budget_credit': None, 'measured_improvement': None,
                  'publication_authorized': False}
        for row in learned['candidates']:
            candidate = row['compiled']['capability']
            same = all(candidate[k] == cap[k] for k in ('contract', 'implementation', 'dependencies'))
            if same:
                result['rejected'].append({'reason': 'unchanged_abstraction', 'capability': capability_ref(candidate)})
                continue
            if candidate['certification'] != 'candidate' or candidate['lifecycle'] != 'build_only':
                raise ValueError('evolution_candidate_cannot_self_certify')
            item = copy.deepcopy(row)
            item['evolution'] = {'previous': prior_ref, 'feedback_ids': ids,
                                 'proposal': result['proposal_evidence'],
                                 'feedback': result['feedback_evidence']}
            result['candidates'].append(item)
        if not result['candidates']:
            result['status'] = 'deferred'
        save(directory / 'result.json', result)
        return result
    except BaseException as error:
        save(directory / 'failure.json', {'status': 'interrupted' if isinstance(error, (KeyboardInterrupt, SystemExit)) else 'failed',
                                         'error': type(error).__name__ + ':' + str(error),
                                         'budget_credit': None})
        raise


def record_relation(feedback, *, relation, subject, beneficiary, scope, evidence,
                    status='passed', cost=None):
    """Import a host-extracted relation with independently retained witnesses.

    The caller is the trusted trace/compiler/verifier adapter, never a proposal.
    A hash proves source consistency, not that arbitrary JSON is trustworthy.
    Exact relation fields bind the host observation to its original witnesses.
    For runtime/compile relations, native artifacts are additionally inspected.
    """
    if relation not in ('proposed_parent', 'material_read', 'compile_ref', 'runtime_call', 'verify_used'):
        raise ValueError('evolution_relation_requires_independent_measurement')
    row = json.loads(verify(evidence))
    expected = {'owner': feedback.owner, 'relation': relation, 'subject': subject,
                'beneficiary': beneficiary, 'scope': scope, 'status': status}
    if any(row.get(key) != value for key, value in expected.items()) or not row.get('sources'):
        raise ValueError('evolution_relation_binding_changed')
    sources = [json.loads(verify(ref)) for ref in row['sources']]
    for source in sources:
        artifact = source.get('execution', source)
        if (artifact.get('owner', feedback.owner) != feedback.owner
                or isinstance(source.get('capability'), dict)
                and source['capability'].get('owner') != feedback.owner):
            raise ValueError('evolution_relation_owner_changed')
    if relation == 'compile_ref':
        witnessed = any(isinstance(source.get('capability'), dict)
                        and capability_ref(source['capability']) == beneficiary
                        and subject in source['capability']['dependencies'] for source in sources)
        if not witnessed:
            raise ValueError('evolution_compile_dependency_not_observed')
    if relation == 'runtime_call':
        receipts = [receipt for source in sources
                    for receipt in source.get('execution', source).get('receipts', [])]
        if not any(receipt.get('capability') == subject and receipt.get('status') == 'succeeded'
                   for receipt in receipts):
            raise ValueError('evolution_runtime_call_not_observed')
    return feedback.observe(stage='construction', relation=relation, subject=subject,
                            beneficiary=beneficiary, scope=scope, status=status, cost=cost,
                            evidence=[evidence, *row['sources']])


def record_measured_effect(feedback, *, subject, scope, dimension, candidate_arm,
                           plan_ref, observations_ref, registry_ref, evidence_root, directory):
    """Remeasure the existing frozen study; reject text-only benefit claims.

    Requires a single-capability treatment contrast for the requested value
    dimension. The original study checks every failed/retried request, ownership,
    independent quality evidence and unknown cost. No spendable credit is made.
    """
    from .efficiency_rsi_measurement import measure_study
    if dimension not in ('execution', 'creation'):
        raise ValueError('evolution_value_dimension_invalid')
    refs = [plan_ref, observations_ref, registry_ref]
    plan, observations, registry = [json.loads(verify(ref)) for ref in refs]
    arms = {arm['id']: arm for arm in plan['arms']}
    baseline = arms[plan['baseline_arm']]
    treatment = arms[candidate_arm]
    key = 'build' if dimension == 'creation' else 'execution'
    other = 'execution' if key == 'build' else 'build'
    before, after = baseline[key + '_capabilities'], treatment[key + '_capabilities']
    if (subject in before or subject not in after
            or sorted(before, key=lambda r: r['id']) != sorted([r for r in after if r != subject], key=lambda r: r['id'])
            or baseline[other + '_capabilities'] != treatment[other + '_capabilities']
            or baseline[other + '_snapshot_sha256'] != treatment[other + '_snapshot_sha256']):
        raise ValueError('evolution_single_capability_contrast_required')
    report = measure_study(plan, observations, registry=registry, evidence_root=evidence_root)
    comparisons = [r for r in report['comparisons'] if r['candidate_arm'] == candidate_arm]
    expected_phase = 'construction' if dimension == 'creation' else 'execution'
    if not comparisons or any(r['phase'] != expected_phase for r in comparisons):
        raise ValueError('evolution_measurement_phase_changed')
    # Pin all quality/artifact files that the original measurement actually used.
    root = Path(evidence_root).resolve()
    originals = [(plan['evaluator']['ref'], plan['evaluator']['sha256'])]
    for attempt in observations['attempts']:
        if attempt['artifact_ref'] is not None:
            originals.append((attempt['artifact_ref'], attempt['artifact_sha256']))
        quality = attempt.get('quality')
        if quality:
            originals.extend((ref['ref'], ref['sha256']) for check in quality['payload']['checks'] for ref in check['evidence'])
    for path, sha in originals:
        target = (root / path).resolve()
        if not target.is_relative_to(root):
            raise ValueError('evolution_measurement_evidence_outside_root')
        ref = {'path': str(target), 'sha256': sha}
        verify(ref)
        refs.append(ref)
    directory = Path(directory)
    directory.mkdir(parents=True, mode=0o700, exist_ok=False)
    save(directory / 'measurement.json', report)
    refs.append(file_ref(directory / 'measurement.json'))
    resolved = report['complete'] and all(row['resolved'] for row in comparisons)
    quality = ('passed' if resolved and all(row['candidate_outcome'] == 'success' for row in comparisons)
               else 'failed' if resolved and all(row['candidate_outcome'] in ('failed', 'budget_exhausted') for row in comparisons)
               else 'unknown')
    fact = {'stage': 'construction' if dimension == 'creation' else 'execution',
            'relation': 'measured_causal_effect', 'subject': copy.deepcopy(subject),
            'beneficiary': None, 'scope': scope, 'status': quality,
            'cost': report['arms'][candidate_arm]['allocated_cost']['model_usd'],
            'evidence': refs, 'opportunity': None, 'benefit': None,
            'value_dimension': dimension, 'comparisons': comparisons, 'comparison_resolved': resolved,
            'total_economic_benefit': None, 'budget_credit': None,
            'scope_limit': 'frozen_single_capability_contrast_not_universal_causality'}
    identity = capability_digest(fact)
    with feedback.update() as state:
        state['facts'][identity] = fact
    return identity
