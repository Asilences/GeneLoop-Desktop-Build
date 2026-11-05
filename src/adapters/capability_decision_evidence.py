"""Host-approved decision evidence over original task and construction records.

Projection approval is supplied by a trusted host. It grants no execution or
certification authority. Raw conversation content stays in original evidence.
"""
from __future__ import annotations

import copy
import importlib.util
import json
from pathlib import Path

from .capability_contract import capability_digest
from .capability_feedback import file_ref, verify
from .capability_improvement import save
from .capability_trajectory import project_web_task
from .capability_construction_history import build_history

CONTEXT_FORMAT = 'capability_decision_context_v1'
FORMAT = 'capability_decision_evidence_v1'
CONTEXT_FIELDS = {'objective', 'state', 'remaining_judgments', 'interactions', 'outcome'}


def _context(reference, owner, evidence, interactions):
    value = json.loads(verify(reference))
    if (not isinstance(value, dict) or set(value) != CONTEXT_FIELDS | {'format', 'owner', 'source_evidence'}
            or value['format'] != CONTEXT_FORMAT or value['owner'] != owner
            or value['source_evidence'] != evidence):
        raise ValueError('decision_context_approval_changed')
    for ref in evidence:
        verify(ref)
    for field in ('objective', 'state', 'outcome'):
        if not isinstance(value[field], str) or not value[field].strip() or len(value[field]) > 2000:
            raise ValueError('decision_context_text_invalid')
    judgments = value['remaining_judgments']
    if (not isinstance(judgments, list) or len(judgments) > 12
            or any(not isinstance(text, str) or not text.strip() or len(text) > 1000 for text in judgments)):
        raise ValueError('decision_context_judgments_invalid')
    summaries = value['interactions']
    if not isinstance(summaries, list) or len(summaries) > 12:
        raise ValueError('decision_context_interactions_invalid')
    indices = {item['event_index']: item['kind'] for item in interactions}
    for item in summaries:
        if (not isinstance(item, dict) or set(item) != {'event_index', 'kind', 'summary'}
                or type(item['event_index']) is not int or indices.get(item['event_index']) != item['kind']
                or not isinstance(item['summary'], str) or not item['summary'].strip()
                or len(item['summary']) > 1000):
            raise ValueError('decision_context_interaction_not_observed')
    return {field: copy.deepcopy(value[field]) for field in sorted(CONTEXT_FIELDS)}


def _web(directory, owner):
    trace = project_web_task(directory, owner)
    evidence = trace['evidence']
    events_ref = next(ref for ref in evidence if Path(ref['path']).name == 'events.jsonl')
    events = [json.loads(line) for line in verify(events_ref).decode('utf-8').splitlines() if line]
    effective_ref = next(ref for ref in evidence if Path(ref['path']).name == 'effective-config.json')
    start = json.loads(verify(effective_ref)).get('trace_start_index', 0)
    interactions = [{'kind': 'clarification', 'event_index': step['call_event_index'],
                     'result_event_index': step['result_event_index'], 'call_id': step['call_id'],
                     'status': step['status']}
                    for step in trace['steps'] if step['tool'] == 'ask_user_question']
    interactions.extend({'kind': 'user_message', 'event_index': index}
                        for index, event in enumerate(events) if index >= start
                        and event.get('type') == 'user/message'
                        and event.get('data', {}).get('source', {}).get('kind') == 'user')
    directory = Path(directory).resolve()
    if directory.parent.name != 'tasks':
        raise ValueError('decision_task_layout_invalid')
    output = directory.parent.parent
    state = json.loads(verify(next(ref for ref in evidence if Path(ref['path']).name == 'task-state.json')))
    request = json.loads(verify(next(ref for ref in evidence if Path(ref['path']).name == 'task.json')))
    session = state.get('session_id')
    if session is not None and (not isinstance(session, str) or not session
            or request.get('session_id') != session):
        raise ValueError('decision_session_lineage_changed')
    if not session and not state.get('source_task_id'):
        raise ValueError('decision_independent_lineage_required')
    # Use the existing account-local learner's comparison/parent ownership.
    # Its legacy fallback is additionally conservative for decision strategies:
    # multiple tasks in the same conversation remain one source.
    script = Path(__file__).resolve().parents[2] / 'scripts/learn-web-ppt-tasks.py'
    spec = importlib.util.spec_from_file_location('decision_existing_ppt_lineage', script)
    worker = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(worker)
    root = worker.decision_root(output, trace['task_id'], {'user': owner}, request, state)
    if root.startswith('web-') and not root.startswith('web-parent-'):
        if session:
            root = 'web-parent-' + session
        elif state.get('source_task_id') == trace['task_id']:
            raise ValueError('decision_independent_lineage_required')
    for path in (output / 'comparisons.json', directory / 'ppt-learning-delivery.json'):
        if path.exists():
            evidence.append(file_ref(path))
    identity = capability_digest({'owner': owner, 'decision_root': root})
    return {'task_id': trace['task_id'], 'source_identity': identity,
            'stage': 'execution', 'status': 'passed' if trace['status'] == 'completed' else 'failed',
            'quality': trace['quality'], 'counterexample': False,
            'evidence': evidence, 'interaction_evidence': interactions,
            'observed_cost_usd': None, 'cost_attribution': 'unknown; task terminal status is not a quality review'}


def _construction(records, task):
    history = build_history(records, task)
    evidence = [task, *records]
    for record in records:
        raw = json.loads(verify(record))
        evidence.extend(raw['sources'].values())
        verification = raw.get('verification')
        if verification and verification.get('evidence_ref'):
            evidence.append(verification['evidence_ref'])
    unique = {capability_digest(ref): ref for ref in evidence}
    rows = history['attempts']
    return {'task_id': task['sha256'], 'source_identity': capability_digest({'task_sha256': task['sha256']}),
            'stage': 'construction', 'status': 'passed' if history['first_quality_success'] else 'unknown',
            'quality': 'independent_verification_passed' if history['first_quality_success'] else 'unreviewed',
            'counterexample': False, 'evidence': list(unique.values()), 'interaction_evidence': [],
            'observed_cost_usd': history['construction_model_usd_decimal'],
            'cost_attribution': history['cost_scope'],
            'construction_outcomes': [{'status': row['status'], 'error': row['error'],
                                       'verification_status': (row['verification'] or {}).get('status')}
                                      for row in rows]}


def inspect_decision(reference, owner):
    """Rebuild source facts and approved semantic context before every use."""
    record = json.loads(verify(reference))
    if (not isinstance(record, dict) or record.get('format') != FORMAT
            or record.get('owner') != owner):
        raise ValueError('decision_evidence_owner_changed')
    if not isinstance(record.get('relation'), str) or not record['relation'].strip():
        raise ValueError('decision_relation_required')
    source = record['source']
    if source['kind'] == 'web_task':
        row = _web(source['directory'], owner)
    elif source['kind'] == 'construction':
        row = _construction(source['records'], source['task'])
    else:
        raise ValueError('decision_source_kind_invalid')
    if row['evidence'] != record['source_evidence']:
        raise ValueError('decision_source_evidence_changed')
    context = _context(record['approved_context'], owner, row['evidence'], row['interaction_evidence'])
    row.update(relation=record['relation'], capabilities=record['capabilities'], steps=[],
               observation_level='host_approved_decision_context', model_decision_count=None,
               decision_context=context)
    row['evidence'] = [*row['evidence'], record['approved_context'], reference]
    return row


def _record(source, owner, relation, approved_context, output, capabilities):
    row = _web(source['directory'], owner) if source['kind'] == 'web_task' else _construction(source['records'], source['task'])
    _context(approved_context, owner, row['evidence'], row['interaction_evidence'])
    if not isinstance(relation, str) or not relation.strip():
        raise ValueError('decision_relation_required')
    if not isinstance(capabilities, (tuple, list)):
        raise ValueError('decision_capabilities_invalid')
    value = {'format': FORMAT, 'owner': owner, 'relation': relation, 'source': source,
             'source_evidence': row['evidence'], 'approved_context': approved_context,
             'capabilities': list(capabilities)}
    path = Path(output)
    save(path, value)
    return file_ref(path)


def record_web_decision(task, owner, *, relation, approved_context, output, capabilities=()):
    """Index an approved task projection; no raw task text is added to context."""
    return _record({'kind': 'web_task', 'directory': str(Path(task).resolve())}, owner, relation,
                   approved_context, output, capabilities)


def record_construction_decision(records, task, owner, *, relation, approved_context, output, capabilities=()):
    """Reuse captured attempts and their original ownership-aware accounting."""
    return _record({'kind': 'construction', 'records': list(records), 'task': task}, owner, relation,
                   approved_context, output, capabilities)
