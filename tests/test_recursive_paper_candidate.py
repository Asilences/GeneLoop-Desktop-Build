"""Boundary/input projection diagnostics; real Script acceptance is separate."""
import copy
import importlib.util
import json
from pathlib import Path

import pytest

from src.adapters.capability_builder import compile_proposal
from src.adapters.capability_contract import create_capability, create_capability_snapshot, capability_ref, capability_digest
from src.adapters.capability_feedback import file_ref
from tests.test_capability_source_authoring import native, RECORD, DELTA, PROJECT, PAIR, envelope

PATH = Path(__file__).resolve().parents[1] / 'scripts/validate-recursive-paper-candidate.py'
spec = importlib.util.spec_from_file_location('recursive_paper_candidate', PATH)
runner = importlib.util.module_from_spec(spec)
spec.loader.exec_module(runner)


def put(path, value):
    path.write_text(json.dumps(value))
    return file_ref(path)


@pytest.fixture
def boundary(tmp_path):
    c = native('observed-c', PROJECT, RECORD)
    report = native('observed-report', {'type': 'object', 'properties': {'before': RECORD, 'after': RECORD},
                    'required': ['before', 'after'], 'additionalProperties': False}, envelope(DELTA))
    def obj(**fields): return {'kind': 'object', 'fields': fields}
    def inp(key): return {'kind': 'input', 'path': [key]}
    def step(identity): return {'kind': 'step', 'step_id': identity, 'path': []}
    original_steps = [
        {'id': 'old', 'capability': capability_ref(c), 'arguments': obj(project=inp('before'))},
        {'id': 'new', 'capability': capability_ref(c), 'arguments': obj(project=inp('after'))},
        {'id': 'report', 'capability': capability_ref(report), 'arguments': obj(before=step('old'), after=step('new'))}]
    root = create_capability({'owner': 'owner', 'contract': {'input_schema': PAIR, 'output_schema': DELTA, 'effects': ['read']},
        'implementation': {'kind': 'composition', 'steps': original_steps,
                           'output': {'kind': 'step', 'step_id': 'report', 'path': ['value']}},
        'dependencies': sorted([capability_ref(c), capability_ref(report)], key=lambda r: r['id'])},
        {'lifecycle': 'active', 'certification': 'certified', 'migration': 'testing'})
    snapshot = create_capability_snapshot('owner', [capability_ref(c), capability_ref(report), capability_ref(root)], [c, report, root])
    proposal = {'format': 'capability_compose_proposal_v1', 'owner': 'owner',
        'contract': {'input_schema': {'type': 'object', 'properties': {'next_path': {'type': 'string'}, 'prior_score': {'type': 'integer'}},
          'required': ['next_path', 'prior_score'], 'additionalProperties': False},
          'output_schema': envelope(DELTA), 'effects': ['read']},
        'steps': [{'id': 'call0', 'capability': capability_ref(c), 'arguments': obj(project=inp('next_path'))},
                  {'id': 'call1', 'capability': capability_ref(report),
                   'arguments': obj(before=obj(score=inp('prior_score')), after=step('call0'))}],
        'output': step('call1')}
    trace = {'snapshot': snapshot, 'execution_ref': put(tmp_path/'execution.json',
             {'root': capability_ref(root), 'receipts': [{'call_id': 'root', 'parent_call_id': None}],
              'task_id': 'training', 'input_versions': [{'path': '/work/inputs/old.zip', 'sha256': 'a'*64}]}),
             'parent_call_id': 'root', 'digest': 'b'*64, 'owner': 'owner',
             'projection': 'capability_composition_calls_v1', 'steps': []}
    values = [({'project': 'old.zip'}, {'score': 2}), ({'project': 'new.zip'}, {'score': 8}),
              ({'before': {'score': 2}, 'after': {'score': 8}}, {'value': {'delta': 6}, 'stdout': '{"delta":6}'})]
    for index, (node, (arguments, result)) in enumerate(zip(original_steps, values)):
        trace['steps'].append({'capability': node['capability'], 'call_id': node['id'],
             'runtime_call_id': 'actual-' + str(index), 'arguments': arguments, 'result': result})
    row = {'proposal': proposal, 'compiled': compile_proposal(proposal, snapshot, 'owner'),
           'provenance': {'training': [trace['digest']], 'heldout': ['c'*64], 'evidence': [trace['execution_ref']]}}
    return row, trace


def test_external_previous_C_value_comes_from_actual_observed_arguments(boundary):
    row, trace = boundary
    args, calls = runner.prepare_arguments(row['proposal'], trace)
    assert args == {'next_path': 'new.zip', 'prior_score': 2}
    assert calls == ['actual-1', 'actual-2']
    changed = copy.deepcopy(trace)
    changed['steps'][0]['result']['score'] = 99  # Never infer by repeated tool name.
    assert runner.prepare_arguments(row['proposal'], changed)[0] == args


def test_local_transfer_must_match_observed_result_not_only_tool_sequence(boundary):
    row, trace = boundary
    trace['steps'][2]['arguments']['after']['score'] = 999
    with pytest.raises(ValueError, match='observed_arguments_changed'):
        runner.prepare_arguments(row['proposal'], trace)


def test_only_pure_last_step_projection_is_inherited(boundary):
    row, trace = boundary
    compiled, proposal, projection, _ = runner.project_boundary(row, trace)
    assert proposal['steps'] == row['proposal']['steps']
    assert proposal['output'] == {'kind': 'step', 'step_id': 'call1', 'path': ['value']}
    assert proposal['contract']['output_schema'] == DELTA
    assert compiled['capability']['certification'] == 'candidate'
    assert compiled['capability']['lifecycle'] == 'build_only'
    assert projection['original_candidate'] != projection['adapted_candidate']
    assert projection['algorithm_changed'] is False


def test_repeated_candidate_occurrences_are_not_guessed(boundary):
    row, trace = boundary
    trace['steps'].extend(copy.deepcopy(trace['steps'][1:]))
    with pytest.raises(ValueError, match='unique_occurrence_required'):
        runner.prepare_arguments(row['proposal'], trace)


def test_projection_rejects_nonfinal_candidate(boundary):
    row, trace = boundary
    trace['steps'].append(copy.deepcopy(trace['steps'][0]))
    with pytest.raises(ValueError, match='pure_last_output_required'):
        runner.project_boundary(row, trace)


def test_changed_compiled_candidate_identity_is_rejected(boundary):
    row, trace = boundary
    row['compiled']['capability'] = trace['snapshot']['capabilities'][0]
    with pytest.raises(ValueError, match='candidate_identity_changed'):
        runner.project_boundary(row, trace)


def test_preview_writes_no_store_and_executes_no_native_code(tmp_path, monkeypatch, boundary):
    row, trace = boundary
    compiled, proposal, projection, root = runner.project_boundary(row, trace)
    monkeypatch.setattr(runner, 'preflight', lambda value: (row, trace, compiled, proposal, projection, root, []))
    monkeypatch.setattr(runner, 'execute_script', lambda *a, **kw: pytest.fail('preview executed native runtime'))
    result = runner.run_manifest({}, tmp_path/'preview', private_root=tmp_path)
    assert result['status'] == 'preview' and result['total_cost_usd'] is None
    assert result['model_requests'] == 0 and not (tmp_path/'preview/store').exists()
    assert not (tmp_path/'preview/publication').exists()


def test_preflight_failure_is_retained_without_hidden_candidate(tmp_path):
    with pytest.raises(ValueError, match='manifest_invalid'):
        runner.run_manifest({}, tmp_path/'failed', private_root=tmp_path)
    result = json.loads((tmp_path/'failed/result.json').read_text())
    assert result['status'] == 'failed' and result['quality'] == 'not_reviewed'
    assert result['total_cost_usd'] is None and result['model_requests'] == 0


def test_failed_preparation_keeps_actual_execution_reference(tmp_path, monkeypatch, boundary):
    row, trace = boundary
    compiled, proposal, projection, root = runner.project_boundary(row, trace)
    monkeypatch.setattr(runner, 'preflight', lambda value: (row, trace, compiled, proposal, projection, root, []))
    def fail(snapshot, selected, libraries, inputs, args, directory, task_id):
        directory.mkdir()
        put(directory/'trace.json', {'status': 'denied', 'task_id': task_id})
        raise ValueError('diagnostic_permission_denied')
    monkeypatch.setattr(runner, 'execute_script', fail)
    manifest = {'libraries': [], 'cases': {'validation': {'id': 'fresh', 'input': {}, 'inputs': []}}}
    with pytest.raises(ValueError, match='diagnostic_permission_denied'):
        runner.run_manifest(manifest, tmp_path/'failure', private_root=tmp_path, execute=True)
    result = json.loads((tmp_path/'failure/result.json').read_text())
    assert result['status'] == 'failed' and result['preparation_runs'][0]['status'] == 'failed'
    assert result['preparation_runs'][0]['execution'] == file_ref(tmp_path/'failure/prepare-validation/trace.json')
    assert result['preparation_runs'][0]['total_cost_usd'] is None
    assert result['published_before_failure'] is False


def test_cannot_write_into_existing_or_public_output(tmp_path):
    with pytest.raises(ValueError, match='private_output_required'):
        runner.run_manifest({}, tmp_path, private_root=tmp_path)
    output = tmp_path/'existing'; output.mkdir()
    with pytest.raises(FileExistsError):
        runner.run_manifest({}, output, private_root=tmp_path)
