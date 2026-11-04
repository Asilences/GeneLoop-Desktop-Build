"""Publish original learner candidates through the original local CapabilityStore.

The verifier freezes an actual held-out Runtime result and checks source
equivalence on a fresh native execution. Semantic benchmark quality remains
with the original task verifier, and later consumption is recorded separately.
"""
from __future__ import annotations

import copy
import json
from pathlib import Path
import os
import subprocess
import sys
import time

from jsonschema import Draft202012Validator

from .capability_contract import capability_digest, capability_ref, validate_capability_snapshot
from .capability_feedback import file_ref, verify
from .capability_improvement import save
from .capability_motif_learning import _at, _bind, _checked, learn_capability_motifs
from .capability_scene import ROOT


DRIVER = ROOT / 'scripts/benchmark-capability-store.mjs'


def _bridge(request, output=None):
    process = subprocess.run(['node', str(DRIVER)], input=json.dumps(request, ensure_ascii=False),
        cwd=ROOT, text=True, encoding='utf-8', capture_output=True, timeout=180,
        env={**os.environ, 'SSS_PYTHON': os.environ.get('SSS_PYTHON', sys.executable)})
    if output is not None:
        Path(output, 'store-driver.stdout.json').write_text(process.stdout, encoding='utf-8')
        Path(output, 'store-driver.stderr.txt').write_text(process.stderr, encoding='utf-8')
    try:
        result = json.loads(process.stdout)
    except ValueError as error:
        raise ValueError('benchmark_store_bridge_invalid_result') from error
    if process.returncode or result.get('status') == 'failed':
        raise ValueError('benchmark_store_bridge_failed:' + str(result.get('error')))
    return result


def original_store_catalog(seed, store_directory):
    """Read the original Store history and expose published roots with the seed."""
    seed = validate_capability_snapshot(seed)
    directory = Path(store_directory).resolve()
    if not directory.exists():
        return {'snapshot': seed, 'head': None, 'catalog': [], 'publications': []}
    return _bridge({'action': 'catalog', 'owner': seed['owner'],
                    'store_directory': str(directory), 'seed': seed})


def _occurrence(proposal, trace):
    expected = [step['capability'] for step in proposal['steps']]
    steps = trace['steps']
    starts = [index for index in range(len(steps) - len(expected) + 1)
              if [step['capability'] for step in steps[index:index + len(expected)]] == expected]
    if len(starts) != 1:
        raise ValueError('benchmark_store_unique_observed_occurrence_required')
    return steps[starts[0]:starts[0] + len(expected)]


def prepare_witnessed_case(candidate, trace):
    """Recover candidate inputs solely from the learner's explicit projections."""
    proposal = candidate['proposal']
    observed = _occurrence(proposal, trace)
    arguments = {}
    for binding in candidate['provenance']['source_input_bindings']:
        index = binding['step_index']
        if (type(index) is not int or not 0 <= index < len(observed)
                or binding['capability'] != observed[index]['capability']):
            raise ValueError('benchmark_store_input_projection_changed')
        value = _at(observed[index]['arguments'], binding['argument_path'])
        key = binding['input_name']
        if key in arguments and capability_digest(arguments[key]) != capability_digest(value):
            raise ValueError('benchmark_store_input_projection_conflict')
        arguments[key] = copy.deepcopy(value)
    Draft202012Validator(proposal['contract']['input_schema']).validate(arguments)
    results = {}
    for step, actual in zip(proposal['steps'], observed):
        bound = _bind(step['arguments'], arguments, results)
        if capability_digest(bound) != capability_digest(actual['arguments']):
            raise ValueError('benchmark_store_observed_arguments_changed')
        results[step['id']] = actual['result']
    expected = _bind(proposal['output'], arguments, results)
    return {'source_task_id': trace['task_id'], 'source_fingerprint': trace['task_fingerprint'],
            'source_trace_digest': trace['digest'], 'input': arguments,
            'expected_result': copy.deepcopy(expected),
            'source_executions': [copy.deepcopy(step['receipt_ref']) for step in observed]}


def prepare_recursive_publication(candidate, trace_refs, materials):
    """Rebuild the same original learner result before granting validation."""
    catalog = materials.catalog()
    owner = materials.owner
    traces = [_checked(json.loads(verify(reference)), owner) for reference in trace_refs]
    by_digest = {trace['digest']: trace for trace in traces}
    if len(by_digest) != len(traces):
        raise ValueError('benchmark_store_duplicate_learning_trace')
    provenance = candidate['provenance']
    expected = provenance['training'] + provenance['heldout']
    if set(expected) != set(by_digest) or len(expected) != len(by_digest):
        raise ValueError('benchmark_store_learning_sources_changed')
    training = [by_digest[digest] for digest in provenance['training']]
    heldout = [by_digest[digest] for digest in provenance['heldout']]
    if len(training) < 2 or not heldout:
        raise ValueError('benchmark_store_learning_split_required')
    snapshot = training[0]['snapshot']
    if any(trace['snapshot']['digest'] != snapshot['digest'] for trace in traces):
        raise ValueError('benchmark_store_learning_snapshot_changed')
    learned = learn_capability_motifs(training, heldout, snapshot, regions=provenance.get('regions'))
    if not any(capability_digest(row) == capability_digest(candidate) for row in learned['candidates']):
        raise ValueError('benchmark_store_original_learner_candidate_required')
    compiled = candidate['compiled']
    compiled_snapshot = validate_capability_snapshot(compiled['snapshot'], owner)
    selected = capability_ref(compiled['capability'])
    if (compiled_snapshot['roots'] != [selected] or compiled['capability']['certification'] != 'candidate'
            or compiled['capability']['implementation']['kind'] != 'composition'):
        raise ValueError('benchmark_store_composition_candidate_required')
    available = {cap['id']: cap for cap in catalog['snapshot']['capabilities']}
    for cap in compiled_snapshot['capabilities']:
        if cap['id'] == selected['id']:
            continue
        actual = available.get(cap['id'])
        if actual is None or capability_ref(actual) != capability_ref(cap):
            raise ValueError('benchmark_store_native_dependency_unavailable')
        if cap['implementation']['kind'] == 'legacy':
            if cap['implementation']['legacy_ref']['backend'] != 'script_motif':
                raise ValueError('benchmark_store_native_script_backend_required')
            if set(cap['contract']['input_schema'].get('properties', {})) != {'value'}:
                raise ValueError('benchmark_store_file_path_bindings_pending')
    case = prepare_witnessed_case(candidate, heldout[0])
    case['source_trace'] = trace_refs[traces.index(heldout[0])]
    return {'seed': catalog['snapshot'], 'libraries': catalog['libraries'],
            'candidate': compiled, 'root': selected, 'case': case,
            'training_sources': [trace_refs[traces.index(trace)] for trace in training],
            'heldout_sources': [trace_refs[traces.index(trace)] for trace in heldout]}


def publish_recursive_candidate(candidate, trace_refs, *, materials, output,
                                expected_latest=None):
    """Publish a source-equivalent composition; unsupported cases remain pending.

    ``expected_latest=None`` captures the current original Store head before the
    publish call. The Store's original CAS still checks that frozen head.
    """
    output = Path(output).resolve()
    output.mkdir(parents=True, exist_ok=False, mode=0o700)
    started = time.monotonic()
    result = {'status': 'pending', 'model_requests': 0, 'creation_value': None,
              'quality_scope': 'heldout_native_source_equivalence',
              'semantic_task_quality': 'original_benchmark_verifier_separate',
              'followup': 'pending_independent_task_consumption'}
    save(output / 'request.json', {'candidate': candidate, 'source_traces': trace_refs})
    try:
        prepared = prepare_recursive_publication(candidate, trace_refs, materials)
        for reference in prepared['libraries']:
            verify(reference)
        store = materials.publication_store
        catalog = original_store_catalog(prepared['seed'], store)
        previous = catalog['head'] if expected_latest is None else expected_latest
        save(output / 'candidate.json', prepared['candidate'])
        save(output / 'source-case.json', prepared['case'])
        plan = {'action': 'publish', 'owner': materials.owner, 'store_directory': str(store),
                'seed': prepared['seed'], 'candidate': file_ref(output / 'candidate.json'),
                'source_case': file_ref(output / 'source-case.json'), 'libraries': prepared['libraries'],
                'expected_latest': previous, 'output': str(output / 'validation')}
        save(output / 'plan.json', plan)
        publication = _bridge(plan, output)
        save(output / 'publication.json', publication)
        result.update(status='published', publication=file_ref(output / 'publication.json'),
                      publication_sha256=publication['publication_sha256'],
                      root=prepared['root'], catalog=materials.catalog())
    except Exception as error:
        result['reason'] = type(error).__name__ + ':' + str(error)
        if (output / 'plan.json').exists():
            result['status'] = 'failed'
    finally:
        result['elapsed_seconds'] = time.monotonic() - started
        save(output / 'result.json', result)
    return result
