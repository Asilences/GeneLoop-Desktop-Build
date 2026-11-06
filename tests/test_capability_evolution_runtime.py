"""T4 actual Runtime -> feedback -> original miner -> Store boundary evolution.

Task inputs, host predicates and boundary proposal are deterministic diagnostics;
no model autonomy or empirical benefit is claimed.
"""
import copy
import json
import os
from pathlib import Path
import subprocess
import sys

import pytest

from src.adapters.capability_contract import capability_ref
from src.adapters.capability_evolution import evolve_abstraction, propose_evolution_boundary, record_relation
from src.adapters.capability_feedback import CapabilityFeedback, file_ref
from src.adapters.capability_motif_learning import capture_capability_trace, learn_capability_motifs

ROOT = Path(__file__).resolve().parents[1]


def native(request):
    result = subprocess.run(['node', str(ROOT / 'tests/fixtures/rae_graph_driver.mjs')],
                            input=json.dumps(request), text=True, capture_output=True, cwd=ROOT,
                            env={**os.environ, 'SSS_PYTHON': sys.executable}, check=True)
    return json.loads(result.stdout)


def put(path, value):
    path.write_text(json.dumps(value), encoding='utf-8')
    return file_ref(path)


def graph(tmp_path, snapshot, task, value):
    refs = {cap['implementation']['legacy_ref']['object_id']: capability_ref(cap)
            for cap in snapshot['capabilities'] if cap['implementation']['kind'] == 'legacy'}
    calls = []
    state = {'value': value}
    for ordinal, operation in enumerate(('increment', 'double', 'subtract')):
        identity = 'n' + str(ordinal)
        executed = native({'action': 'run', 'snapshot': snapshot, 'root': refs[operation],
                           'input': state, 'task_id': task})['execution']
        assert executed['status'] == 'succeeded'
        ref = put(tmp_path / (task + '-' + identity + '.json'), executed)
        binding = {'kind': 'input', 'path': []} if ordinal == 0 else {
            'kind': 'object', 'fields': {'value': {'kind': 'step', 'step_id': 'n' + str(ordinal - 1), 'path': ['value']}}}
        calls.append({'id': identity, 'capability': refs[operation], 'input_binding': binding, 'execution_ref': ref})
        state = executed['result']
    return capture_capability_trace(snapshot, task_id=task, task_input={'value': value},
                                    task_fingerprint='independent-' + task, calls=calls)


def publish(tmp_path, candidate, seed, label, expected_latest=None):
    # The learner's parameterized input name is fixed by the original compiler.
    inputs = candidate['compiled']['capability']['contract']['input_schema']['properties']
    assert len(inputs) == 1
    key = next(iter(inputs))
    count = len(candidate['proposal']['steps'])
    expected = lambda x: {'value': (x + 1) * 2 - (3 if count == 3 else 0)}
    return native({'action': 'publish', 'compiled': candidate['compiled'], 'seed': seed,
                   'directory': str(tmp_path / 'publication'), 'label': label,
                   'expectedLatest': expected_latest,
                   'validation_input': {key: 10}, 'followup_input': {key: 20},
                   'expected_validation': expected(10), 'expected_followup': expected(20)})


def test_feedback_changes_executable_boundary_and_publishes_new_version(tmp_path):
    seed = native({'action': 'seed', 'owner': 'owner'})
    traces = [graph(tmp_path, seed, 'task-' + str(i), value) for i, value in enumerate((1, 4, 9))]
    learned = learn_capability_motifs(traces[:2], traces[2:], seed)
    full = max(learned['candidates'], key=lambda row: len(row['proposal']['steps']))
    assert len(full['proposal']['steps']) == 3
    original = publish(tmp_path, full, seed, 'full')
    prior_ref = capability_ref(full['compiled']['capability'])
    original_bytes = json.dumps(original['publication'], sort_keys=True)
    manager = CapabilityFeedback(tmp_path / 'feedback', 'owner')

    # Reuse really executes, but this wider capability includes an unwanted
    # downstream subtract step for the separate host-defined local obligation.
    key = next(iter(full['compiled']['capability']['contract']['input_schema']['properties']))
    observed = native({'action': 'run', 'snapshot': original['publication']['snapshot'],
                       'root': prior_ref, 'input': {key: 7}, 'task_id': 'local-obligation'})['execution']
    assert observed['status'] == 'succeeded' and observed['result'] != {'value': 16}
    execution_ref = put(tmp_path / 'too-wide-execution.json', observed)
    verdict_ref = put(tmp_path / 'host-local-check.json', {
        'owner': 'owner', 'scope': 'local-transform', 'expected': {'value': 16},
        'actual': observed['result'], 'passed': False, 'execution': execution_ref,
        'reason': 'local_obligation_excludes_downstream_subtract', 'diagnostic': True})
    fact_id = manager.observe(stage='execution', subject=prior_ref, scope='local-transform',
                              status='failed', cost=None, evidence=[execution_ref, verdict_ref])
    prior = put(tmp_path / 'prior-candidate.json', full['compiled'])
    observed_requests = []
    def existing_proposer(request):
        observed_requests.append(request)
        # Deterministic feedback injection for T4: a witnessed local mismatch
        # changes the next proposed boundary; no new policy engine is added.
        failed = any(row['status'] == 'failed' for row in request['values']['execution'].values())
        region = ['n0', 'n1'] if failed else ['n0', 'n1', 'n2']
        return {'feedback_ids': list(request['values']['execution']),
                'regions': {trace['task_id']: region for trace in request['training']}}
    proposed = propose_evolution_boundary(traces[:2], feedback=manager, prior_candidate=prior,
        scope='local-transform', proposer=existing_proposer, directory=tmp_path / 'boundary-proposal', enabled=True)
    assert len(observed_requests) == 1 and len(observed_requests[0]['training']) == 2
    assert traces[2]['task_id'] not in json.dumps(observed_requests[0])
    boundary = proposed['proposal']
    # The host supplies the independent heldout projection; it was never sent
    # to the proposal callback or used to choose this alternative boundary.
    boundary['regions'][traces[2]['task_id']] = ['n0', 'n1']
    evolved = evolve_abstraction(traces[:2], traces[2:], original['library']['snapshot'], feedback=manager,
                                 prior_candidate=prior, proposal=boundary, directory=tmp_path / 'evolution', enabled=True)
    assert evolved['status'] == 'proposed' and evolved['measured_improvement'] is None
    smaller = max(evolved['candidates'], key=lambda row: len(row['proposal']['steps']))
    assert len(smaller['proposal']['steps']) == 2
    new_ref = capability_ref(smaller['compiled']['capability'])
    assert new_ref != prior_ref and smaller['compiled']['capability']['certification'] == 'candidate'
    updated = publish(tmp_path, smaller, seed, 'local', original['result']['publication_sha256'])
    assert updated['result']['followup_passed'] is True
    assert prior_ref in updated['library']['snapshot']['roots'] and new_ref in updated['library']['snapshot']['roots']
    assert json.dumps(original['publication'], sort_keys=True) == original_bytes
    assert manager.read()['facts'][fact_id]['status'] == 'failed'
    assert evolved['budget_credit'] is None and not evolved['publication_authorized']

    # Applying the unchanged downstream step recovers the original complete task.
    local = native({'action': 'run', 'snapshot': updated['library']['snapshot'], 'root': new_ref,
                    'input': {next(iter(smaller['compiled']['capability']['contract']['input_schema']['properties'])): 7},
                    'task_id': 'complete-task'})['execution']
    subtract = next(capability_ref(c) for c in seed['capabilities'] if c['implementation']['legacy_ref']['object_id'] == 'subtract')
    complete = native({'action': 'run', 'snapshot': updated['library']['snapshot'], 'root': subtract,
                       'input': local['result'], 'task_id': 'complete-task'})['execution']
    assert complete['result'] == observed['result']

    # A runtime relation is recorded only from the actual matching receipt.
    actual_ref = put(tmp_path / 'new-execution.json', local)
    witness = put(tmp_path / 'runtime-relation.json', {'owner': 'owner', 'relation': 'runtime_call',
        'subject': new_ref, 'beneficiary': None, 'scope': 'complete-task', 'status': 'passed', 'sources': [actual_ref]})
    identity = record_relation(manager, relation='runtime_call', subject=new_ref, beneficiary=None,
                               scope='complete-task', evidence=witness)
    assert manager.read()['facts'][identity]['benefit'] is None

    changed = copy.deepcopy(boundary)
    changed['regions'][traces[0]['task_id']] = ['n0', 'n2']
    with pytest.raises(ValueError, match='ordered_contiguous'):
        evolve_abstraction(traces[:2], traces[2:], seed, feedback=manager, prior_candidate=prior,
                           proposal=changed, directory=tmp_path / 'invalid', enabled=True)
