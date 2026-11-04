"""T3 wiring: real Runtime calls, original Motif miner/compiler, Store publication.

Synthetic tasks and diagnostic authorization do not establish autonomous RSI.
"""
import copy
import json
import os
from pathlib import Path
import subprocess
import sys

import pytest

from src.adapters.capability_builder import compile_proposal
from src.adapters.capability_contract import capability_digest, capability_ref
from src.adapters.capability_feedback import file_ref
from src.adapters.capability_motif_learning import capture_capability_trace, learn_capability_motifs

ROOT = Path(__file__).resolve().parents[1]
DRIVER = ROOT / 'tests/fixtures/rae_graph_driver.mjs'


def run_driver(request):
    result = subprocess.run(['node', str(DRIVER)], input=json.dumps(request), text=True, encoding='utf-8',
        cwd=ROOT, env={**os.environ, 'SSS_PYTHON': sys.executable}, capture_output=True, timeout=60)
    if result.returncode:
        raise RuntimeError(result.stderr)
    return json.loads(result.stdout)


def put(path, value):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, ensure_ascii=False), encoding='utf-8')
    return file_ref(path)


def call_trace(directory, snapshot, refs, task_id, value, *, role='task'):
    """Execute an observed host-selected graph; learner never receives this route as a target."""
    caps = {c['id']: c for c in snapshot['capabilities']}; calls = []; previous = value
    for index, ref in enumerate(refs):
        parameter = caps[ref['id']]['contract']['input_schema']['required'][0]
        args = {parameter: previous}
        result = run_driver({'action': 'run', 'snapshot': snapshot, 'root': ref, 'input': args, 'task_id': task_id})['execution']
        assert result['status'] == 'succeeded', result
        binding = {'kind': 'input', 'path': ['value']} if index == 0 else {
            'kind': 'step', 'step_id': 'node' + str(index - 1), 'path': ['value']}
        calls.append({'id': 'node' + str(index), 'capability': ref,
                      'input_binding': {'kind': 'object', 'fields': {parameter: binding}},
                      'execution_ref': put(directory / (task_id + '-' + str(index) + '.json'), result)})
        previous = result['result']['value']
    return capture_capability_trace(snapshot, task_id=task_id, task_input={'value': value},
        task_fingerprint=capability_digest({'task': task_id, 'input': value}), calls=calls, role=role)


def publish(directory, seed, compiled, label, input_key, expected):
    return run_driver({'action': 'publish', 'compiled': compiled, 'seed': seed,
        'directory': str(directory), 'label': label, 'validation_input': {input_key: 11},
        'followup_input': {input_key: 17}, 'expected_validation': {'value': expected(11)},
        'expected_followup': {'value': expected(17)}})


@pytest.fixture
def corpus(tmp_path):
    seed = run_driver({'action': 'seed', 'owner': 'rae-closure'})
    by_operation = {c['implementation']['legacy_ref']['object_id']: c for c in seed['capabilities']}
    inc = by_operation['increment']
    # C is an independently published seed abstraction, not a hand-written D.
    c = compile_proposal({'format': 'capability_compose_proposal_v1', 'owner': seed['owner'],
        'contract': copy.deepcopy(inc['contract']), 'steps': [{'id': 'seed', 'capability': capability_ref(inc),
            'arguments': {'kind': 'input', 'path': []}}],
        'output': {'kind': 'step', 'step_id': 'seed', 'path': []}}, seed, seed['owner'])
    published = publish(tmp_path / 'C', seed, c, 'C', 'value', lambda x: x + 1)
    snapshot = published['library']['snapshot']; c_ref = capability_ref(c['capability'])
    refs = [c_ref, capability_ref(by_operation['double'])]
    traces = [call_trace(tmp_path / 'G1', snapshot, refs, 'task-' + str(i), value)
              for i, value in enumerate([2, 4, 7])]
    return seed, snapshot, c_ref, by_operation, traces


def test_real_capability_calls_enter_original_miner_publish_D_and_learn_again_in_G2(tmp_path, corpus):
    seed, snapshot, c_ref, operations, traces = corpus
    learned = learn_capability_motifs(traces[:2], traces[2:], snapshot)
    assert len(learned['candidates']) == 1 and learned['rejected'] == []
    d = learned['candidates'][0]
    assert d['motif']['status'] == 'trace_validated_read_only'
    assert d['motif']['transfer_evidence'][0]['from_tool'] == 'capability_' + c_ref['sha256']
    assert c_ref in d['compiled']['capability']['dependencies']
    # Internal C receipt remains auditable, but C is one node in the learner's G1.
    assert len(traces[0]['steps']) == 2
    first_execution = json.loads(Path(traces[0]['steps'][0]['receipt_ref']['path']).read_text())
    assert len(first_execution['receipts']) == 2
    assert d['compiled']['capability']['certification'] == 'candidate'
    publication = publish(tmp_path / 'D', snapshot, d['compiled'], 'D', 'p0_value', lambda x: 2 * (x + 1))
    next_snapshot = publication['library']['snapshot']; d_ref = capability_ref(d['compiled']['capability'])
    assert d_ref in next_snapshot['roots'] and c_ref in next_snapshot['roots']
    g2 = [call_trace(tmp_path / 'G2', next_snapshot, [d_ref, capability_ref(operations['subtract'])],
                    'next-' + str(i), value) for i, value in enumerate([3, 8, 12])]
    next_learned = learn_capability_motifs(g2[:2], g2[2:], next_snapshot)
    assert len(next_learned['candidates']) == 1
    e = next_learned['candidates'][0]
    assert d_ref in e['compiled']['capability']['dependencies']
    assert c_ref not in e['compiled']['capability']['dependencies']
    assert e['compiled']['snapshot']['capabilities']  # C remains in transitive execution closure.
    final = publish(tmp_path / 'E', next_snapshot, e['compiled'], 'E', 'p0_p0_value', lambda x: 2 * (x + 1) - 3)
    assert final['result']['followup_passed'] is True
    assert learned['creation_value'] is None and learned['model_requests'] == 0


def test_builder_role_uses_identical_extractor_and_compiler(corpus):
    _, snapshot, _, _, traces = corpus
    builders = [capture_capability_trace(t['snapshot'], task_id=t['task_id'], task_input=t['task_input'],
        task_fingerprint=t['task_fingerprint'], calls=t['calls'], role='builder') for t in traces]
    learned = learn_capability_motifs(builders[:2], builders[2:], snapshot)
    assert learned['candidates'][0]['provenance']['roles'] == ['builder']


def test_foreign_owner_changed_evidence_and_reused_tasks_are_rejected(corpus):
    _, snapshot, _, _, traces = corpus
    foreign = copy.deepcopy(traces); foreign[0]['owner'] = 'other'
    with pytest.raises(ValueError, match='owner_changed'):
        learn_capability_motifs(foreign[:2], foreign[2:], snapshot)
    changed = copy.deepcopy(traces); changed[0]['steps'][0]['result']['value'] = 0
    with pytest.raises(ValueError, match='trace_changed'):
        learn_capability_motifs(changed[:2], changed[2:], snapshot)
    with pytest.raises(ValueError, match='independent_tasks_required'):
        learn_capability_motifs(traces[:2], traces[:1], snapshot)
    path = Path(traces[0]['calls'][0]['execution_ref']['path']); path.write_text('{}')
    with pytest.raises(ValueError, match='evidence_changed'):
        learn_capability_motifs(traces[:2], traces[2:], snapshot)


def test_equal_literal_value_is_not_inferred_as_parameter_flow(corpus):
    _, snapshot, _, _, traces = corpus
    independent = []
    for trace in traces:
        calls = copy.deepcopy(trace['calls'])
        calls[1]['input_binding']['fields']['value'] = {'kind': 'literal', 'value': trace['steps'][1]['arguments']['value']}
        independent.append(capture_capability_trace(snapshot, task_id=trace['task_id'], task_input=trace['task_input'],
            task_fingerprint=trace['task_fingerprint'], calls=calls))
    candidate = learn_capability_motifs(independent[:2], independent[2:], snapshot)['candidates'][0]
    assert candidate['motif']['transfer_evidence'] == []
    assert set(candidate['proposal']['contract']['input_schema']['required']) == {'p0_value', 'p1_value'}


def test_declared_binding_and_actual_runtime_arguments_must_agree(corpus):
    _, snapshot, _, _, traces = corpus
    trace = traces[0]; calls = copy.deepcopy(trace['calls'])
    calls[1]['input_binding']['fields']['value'] = {'kind': 'input', 'path': ['value']}
    with pytest.raises(ValueError, match='arguments_changed'):
        capture_capability_trace(snapshot, task_id=trace['task_id'], task_input=trace['task_input'],
            task_fingerprint=trace['task_fingerprint'], calls=calls)


def test_regions_cannot_jump_over_an_unobserved_or_failed_call(corpus):
    _, snapshot, _, _, traces = corpus
    with pytest.raises(ValueError, match='region_invalid'):
        learn_capability_motifs(traces[:2], traces[2:], snapshot,
            regions={t['trace_id']: ['node0', 'invented'] for t in traces})


@pytest.mark.parametrize('change', ['events', 'native', 'parent', 'children', 'guard'])
def test_a_success_label_without_a_consistent_native_execution_tree_is_rejected(tmp_path, corpus, change):
    _, snapshot, _, _, traces = corpus
    trace = traces[0]; calls = copy.deepcopy(trace['calls'])
    execution = json.loads(Path(calls[0]['execution_ref']['path']).read_text())
    root, leaf = execution['receipts']
    if change == 'events': leaf['events'] = []
    elif change == 'native': leaf['backend_receipt']['call_id'] = 'invented'
    elif change == 'parent': leaf['parent_call_id'] = leaf['call_id']
    elif change == 'children': root['child_call_ids'] = []
    else: leaf['events'][1]['payload']['permission_ref'] = 'another-grant'
    calls[0]['execution_ref'] = put(tmp_path / ('tampered-' + change + '.json'), execution)
    with pytest.raises(ValueError, match='capability_motif_'):
        capture_capability_trace(snapshot, task_id=trace['task_id'], task_input=trace['task_input'],
            task_fingerprint=trace['task_fingerprint'], calls=calls)


def test_self_or_forward_dependency_cannot_be_compiled(corpus):
    _, snapshot, _, _, traces = corpus
    proposal = learn_capability_motifs(traces[:2], traces[2:], snapshot)['candidates'][0]['proposal']
    proposal['steps'][0]['arguments']['fields']['value'] = {'kind': 'step', 'step_id': 'call1', 'path': ['value']}
    with pytest.raises(ValueError, match='binding_step_unavailable'):
        compile_proposal(proposal, snapshot, snapshot['owner'])
