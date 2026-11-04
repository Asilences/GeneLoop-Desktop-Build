"""Nested data and composite receipt regression; public synthetic diagnostics.

No private paper traces are embedded; actual Runtime dispatch uses synthetic
Script-shaped completion witnesses, not the production Script sandbox.
"""
import copy
import json
from pathlib import Path
import subprocess

import pytest

from src.adapters.capability_builder import compile_proposal
from src.adapters.capability_contract import capability_digest, capability_ref, create_capability_snapshot
from src.adapters.capability_motif_learning import capture_composition_trace, learn_capability_motifs, _at
from tests.test_capability_motif_learning import put, ROOT


def run(request):
    result = subprocess.run(['node', str(ROOT / 'tests/fixtures/rae_nested_script.mjs')],
        input=json.dumps(request), text=True, encoding='utf-8', capture_output=True, cwd=ROOT, timeout=30)
    assert result.returncode == 0, result.stderr
    return json.loads(result.stdout)


def certified(snapshot, proposal):
    compiled = compile_proposal(proposal, snapshot, snapshot['owner'])
    # Explicit synthetic setup authority. Learning output below stays candidate.
    cap = {**compiled['capability'], 'certification': 'certified', 'lifecycle': 'active'}
    return create_capability_snapshot(snapshot['owner'], [*snapshot['roots'], capability_ref(cap)],
        [*snapshot['capabilities'], cap]), cap


@pytest.fixture
def nested(tmp_path):
    snapshot = run({'action': 'seed'})
    audit, compare = (next(c for c in snapshot['capabilities'] if c['implementation']['legacy_ref']['object_id'] == name)
                      for name in ('audit', 'compare'))
    snapshot, c = certified(snapshot, {'format': 'capability_compose_proposal_v1', 'owner': snapshot['owner'],
        'contract': {**audit['contract'], 'output_schema': audit['contract']['output_schema']['properties']['value']},
        'steps': [{'id': 'audit', 'capability': capability_ref(audit), 'arguments': {'kind': 'input', 'path': []}}],
        'output': {'kind': 'step', 'step_id': 'audit', 'path': ['value']}})
    schema = {'type': 'object', 'properties': {key: {'type': 'string'} for key in ('before', 'after')},
              'required': ['before', 'after'], 'additionalProperties': False}
    snapshot, root = certified(snapshot, {'format': 'capability_compose_proposal_v1', 'owner': snapshot['owner'],
        'contract': {'input_schema': schema, 'output_schema': compare['contract']['output_schema']['properties']['value'], 'effects': ['read']},
        'steps': [*[{'id': key, 'capability': capability_ref(c),
            'arguments': {'kind': 'object', 'fields': {'project': {'kind': 'input', 'path': [key]}}}} for key in ('before', 'after')],
            {'id': 'report', 'capability': capability_ref(compare), 'arguments': {'kind': 'object', 'fields': {
                'value': {'kind': 'object', 'fields': {key: {'kind': 'step', 'step_id': key, 'path': []}
                                                    for key in ('before', 'after')}}}}}],
        'output': {'kind': 'step', 'step_id': 'report', 'path': ['value']}})
    traces = []
    for index, values in enumerate([('empty', 'empty'), ('old', 'old'), ('third', 'empty')]):
        args = dict(zip(('before', 'after'), values)); task_id = 'nested-' + str(index)
        execution = run({'snapshot': snapshot, 'root': capability_ref(root), 'input': args, 'task_id': task_id})['execution']
        assert execution['status'] == 'succeeded', [(row['capability']['id'], row['reason']) for row in execution['receipts']]
        ref = put(tmp_path / (task_id + '.json'), execution)
        traces.append(capture_composition_trace(snapshot, execution_ref=ref, task_input=args,
            task_fingerprint=capability_digest(args)))
    return snapshot, capability_ref(c), traces


def test_original_composite_receipts_discover_unique_suffix_and_execute_typed_candidate(tmp_path, nested):
    snapshot, c_ref, traces = nested
    original = Path(traces[0]['execution_ref']['path']).read_bytes()
    learned = learn_capability_motifs(traces[:2], traces[2:], snapshot)
    assert len(learned['candidates']) == 1 and learned['unsupported_capabilities'] == []
    assert any('non-repeated' in row['reason'] for row in learned['rejected'])
    candidate = learned['candidates'][0]
    assert candidate['compiled']['capability']['certification'] == 'candidate'
    assert candidate['proposal']['steps'][0]['capability'] == c_ref
    arguments = candidate['proposal']['steps'][1]['arguments']['fields']['value']['fields']
    # Both C calls returned identical values in BOTH training traces. Explicit
    # call identity still prevents the earlier C's inputs becoming a false edge.
    assert all(binding['kind'] == 'input' for binding in arguments['before']['fields'].values())
    assert all(binding['kind'] == 'step' for binding in arguments['after']['fields'].values())
    assert any(s['type'] == 'array' for s in candidate['proposal']['contract']['input_schema']['properties'].values())
    witness = traces[2]['steps'][1:]
    inputs = {binding['input_name']: _at(witness[binding['step_index']]['arguments'], binding['argument_path'])
              for binding in candidate['provenance']['source_input_bindings']}
    output = run({'snapshot': candidate['compiled']['snapshot'], 'root': capability_ref(candidate['compiled']['capability']),
        'input': inputs, 'task_id': 'independent-local-execution', 'mode': 'validate'})['execution']
    assert output['status'] == 'succeeded'
    assert output['result'] == witness[-1]['result']
    assert Path(traces[0]['execution_ref']['path']).read_bytes() == original
    assert len(traces[0]['steps']) == 3
    assert all(step['parent_runtime_call_id'] == traces[0]['parent_call_id'] for step in traces[0]['steps'])
    assert {step['receipt_ref']['path'] for step in traces[0]['steps']} == {traces[0]['execution_ref']['path']}


@pytest.mark.parametrize('change', ['output', 'rehash_output', 'script_version', 'arguments', 'parent', 'missing_output'])
def test_original_receipt_values_and_lineage_cannot_be_forged(tmp_path, nested, change):
    snapshot, _, traces = nested
    trace = traces[0]; execution = json.loads(Path(trace['execution_ref']['path']).read_text(encoding='utf-8'))
    leaf = next(row for row in execution['receipts'] if row['kind'] == 'legacy')
    native = leaf['backend_receipt']['native_receipt']
    if change in ('output', 'rehash_output'):
        native['output'] = '{"name":"changed","records":[]}'
        if change == 'rehash_output':
            import hashlib
            native['output_sha256'] = hashlib.sha256(native['output'].encode()).hexdigest()
    elif change == 'script_version': native['script_version']['object_sha256'] = '0' * 64
    elif change == 'arguments': leaf['arguments_sha256'] = '0' * 64
    elif change == 'parent': leaf['parent_call_id'] = execution['receipts'][0]['call_id']
    else: native.pop('output')
    ref = put(tmp_path / ('changed-' + change + '.json'), execution)
    with pytest.raises(ValueError, match='capability_motif_'):
        capture_composition_trace(snapshot, execution_ref=ref, task_input=trace['execution_input'],
            task_fingerprint=trace['task_fingerprint'])


def test_changed_projection_reused_tasks_and_leaf_scope_are_rejected(nested):
    snapshot, _, traces = nested
    changed = copy.deepcopy(traces)
    changed[0]['steps'][0]['arguments']['project'] = 'forged'
    with pytest.raises(ValueError, match='trace_changed'):
        learn_capability_motifs(changed[:2], changed[2:], snapshot)
    with pytest.raises(ValueError, match='independent_tasks_required'):
        learn_capability_motifs(traces[:2], traces[:1], snapshot)
    execution = json.loads(Path(traces[0]['execution_ref']['path']).read_text(encoding='utf-8'))
    leaf = next(row for row in execution['receipts'] if row['kind'] == 'legacy')
    with pytest.raises(ValueError, match='composition_parent_required'):
        capture_composition_trace(snapshot, execution_ref=traces[0]['execution_ref'],
            task_input=traces[0]['execution_input'], task_fingerprint=traces[0]['task_fingerprint'],
            parent_call_id=leaf['call_id'])
