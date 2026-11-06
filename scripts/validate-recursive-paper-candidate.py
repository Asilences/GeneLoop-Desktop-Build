#!/usr/bin/env python3
"""Replay a witnessed local boundary, then use the original Paper publication cycle.

Default preview. No model calls, algorithm generation, evaluator changes or
production Store writes. Full-root input preparation is included in the audit;
this is a mechanism acceptance, not an efficiency comparison.
"""
from __future__ import annotations

import argparse
import copy
import json
import os
from pathlib import Path
import signal
import sys
import time

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from jsonschema import Draft202012Validator
from src.adapters.capability_builder import compile_proposal
from src.adapters.capability_contract import capability_digest, capability_ref, validate_capability_snapshot
from src.adapters.capability_feedback import file_ref
from src.adapters.capability_improvement import evidence, save, validate
from src.adapters.capability_motif_learning import _bind, _checked, capture_composition_trace
from src.adapters.capability_script_execution import execute as execute_script
from src.adapters.capability_scene import run_child


def read(ref):
    validate('evidence', ref)
    return json.loads(evidence(ref))


def occurrence(proposal, trace):
    wanted = [step['capability'] for step in proposal['steps']]
    steps = trace['steps']
    starts = [i for i in range(len(steps) - len(wanted) + 1)
              if [row['capability'] for row in steps[i:i + len(wanted)]] == wanted]
    if len(starts) != 1:
        raise ValueError('paper_recursive_unique_occurrence_required')
    start = starts[0]
    return steps[start:start + len(wanted)]


def prepare_arguments(proposal, trace):
    """Invert only explicit input leaves, then recheck every original binding."""
    matched = occurrence(proposal, trace)
    arguments = {}
    def visit(binding, actual):
        if binding['kind'] == 'input':
            if len(binding['path']) != 1:
                raise ValueError('paper_recursive_flat_external_input_required')
            key = binding['path'][0]
            if key in arguments and capability_digest(arguments[key]) != capability_digest(actual):
                raise ValueError('paper_recursive_external_input_conflict')
            arguments[key] = copy.deepcopy(actual)
        elif binding['kind'] == 'object':
            for key, child in binding['fields'].items():
                visit(child, actual[key])
        elif binding['kind'] == 'array':
            for index, child in enumerate(binding['items']):
                visit(child, actual[index])
    for step, observed in zip(proposal['steps'], matched):
        visit(step['arguments'], observed['arguments'])
    Draft202012Validator(proposal['contract']['input_schema']).validate(arguments)
    results = {}
    for step, observed in zip(proposal['steps'], matched):
        if capability_digest(_bind(step['arguments'], arguments, results)) != capability_digest(observed['arguments']):
            raise ValueError('paper_recursive_observed_arguments_changed')
        results[step['id']] = observed['result']
    return arguments, [row['runtime_call_id'] for row in matched]


def project_boundary(row, trace):
    """Inherit only the witnessed root's pure last-step output path."""
    snapshot = validate_capability_snapshot(trace['snapshot'])
    original = compile_proposal(row['proposal'], snapshot, snapshot['owner'])
    if capability_ref(original['capability']) != capability_ref(row['compiled']['capability']):
        raise ValueError('paper_recursive_candidate_identity_changed')
    execution = read(trace['execution_ref'])
    outer = [r for r in execution['receipts'] if r['parent_call_id'] is None]
    if len(outer) != 1 or trace['parent_call_id'] != outer[0]['call_id']:
        raise ValueError('paper_recursive_root_projection_required')
    root = next(cap for cap in snapshot['capabilities'] if capability_ref(cap) == execution['root'])
    matched = occurrence(row['proposal'], trace)
    output = root['implementation']['output']
    if (root['implementation']['kind'] != 'composition' or root['certification'] != 'certified'
            or root['lifecycle'] != 'active' or matched[-1] != trace['steps'][-1]
            or output['kind'] != 'step' or output['step_id'] != matched[-1]['call_id']):
        raise ValueError('paper_recursive_pure_last_output_required')
    proposal = copy.deepcopy(row['proposal'])
    proposal['output'] = {'kind': 'step', 'step_id': proposal['steps'][-1]['id'], 'path': copy.deepcopy(output['path'])}
    proposal['contract']['output_schema'] = copy.deepcopy(root['contract']['output_schema'])
    adapted = compile_proposal(proposal, snapshot, snapshot['owner'])
    prepare_arguments(proposal, trace)
    projection = {'source_root': execution['root'], 'source_execution': trace['execution_ref'],
                  'source_trace_sha256': trace['digest'], 'source_output_binding': output,
                  'original_candidate': capability_ref(original['capability']),
                  'adapted_candidate': capability_ref(adapted['capability']),
                  'operation': 'inherit_original_pure_last_step_output_path',
                  'algorithm_changed': False}
    return adapted, proposal, projection, execution['root']


def preflight(manifest):
    if not isinstance(manifest, dict) or set(manifest) != {'candidate', 'source_trace', 'libraries', 'cases'}:
        raise ValueError('paper_recursive_manifest_invalid')
    row = read(manifest['candidate'])
    trace = _checked(read(manifest['source_trace']), row['compiled']['capability']['owner'])
    if trace['projection'] != 'capability_composition_calls_v1':
        raise ValueError('paper_recursive_composition_trace_required')
    provenance = row['provenance']
    if trace['digest'] not in [*provenance['training'], *provenance['heldout']]:
        raise ValueError('paper_recursive_source_not_learning_evidence')
    adapted, proposal, projection, root = project_boundary(row, trace)
    refs = [manifest['candidate'], manifest['source_trace'], *provenance['evidence']]
    if not isinstance(manifest['libraries'], list) or not manifest['libraries']:
        raise ValueError('paper_recursive_native_libraries_required')
    refs += manifest['libraries']
    if set(manifest['cases']) != {'validation', 'followup'}:
        raise ValueError('paper_recursive_two_independent_cases_required')
    past = [read(ref) for ref in provenance['evidence']]
    task_ids = {record.get('task_id') for record in past}
    fingerprints = {capability_digest(sorted(item['sha256'] for item in record['input_versions']))
                    for record in past if record.get('input_versions')}
    for case in manifest['cases'].values():
        if set(case) != {'id', 'input', 'inputs', 'specification'} or not isinstance(case['id'], str) or not case['id']:
            raise ValueError('paper_recursive_case_invalid')
        if case['id'] in task_ids or not case['inputs']:
            raise ValueError('paper_recursive_fresh_case_required')
        paths = []
        for item in case['inputs']:
            path = item['path']
            if path != '/work/inputs/' + Path(path).name or set(item) != {'path', 'source'}:
                raise ValueError('paper_recursive_input_path_invalid')
            evidence(item['source']); refs.append(item['source']); paths.append(path)
        if len(paths) != len(set(paths)):
            raise ValueError('paper_recursive_input_path_duplicate')
        spec = case['specification']
        if (spec.get('kind') != 'frontier_literal_v1' or spec.get('role') != 'D'
                or len(spec.get('input_paths', [])) != 2 or any(p not in paths for p in spec['input_paths'])):
            raise ValueError('paper_recursive_original_D_oracle_required')
        fingerprint = capability_digest(sorted(item['source']['sha256'] for item in case['inputs']))
        if fingerprint in fingerprints:
            raise ValueError('paper_recursive_fresh_input_versions_required')
        task_ids.add(case['id']); fingerprints.add(fingerprint)
    for ref in refs:
        evidence(ref)
    return row, trace, adapted, proposal, projection, root, refs


def run_manifest(manifest, output, *, execute=False, private_root=None):
    private_root = (ROOT / '.local' if private_root is None else Path(private_root)).resolve()
    output = Path(output).resolve()
    if output == private_root or not output.is_relative_to(private_root):
        raise ValueError('paper_recursive_private_output_required')
    output.mkdir(mode=0o700, parents=True, exist_ok=False)
    manifest = copy.deepcopy(manifest)
    save(output / 'manifest.json', manifest)
    started = time.monotonic()
    result = {'format': 'capability_recursive_paper_acceptance_v1', 'status': 'preview',
              'model_requests': 0, 'model_cost_usd': '0', 'total_cost_usd': None,
              'efficiency_conclusion': None, 'preparation_runs': [], 'quality': 'not_reviewed',
              'scope': 'local_mined_boundary_independent_oracle_and_publication_not_sustained_RSI'}
    try:
        row, trace, compiled, proposal, projection, root, refs = preflight(manifest)
        save(output / 'candidate.json', compiled)
        save(output / 'proposal.json', proposal)
        save(output / 'boundary-projection.json', projection)
        save(output / 'effective.json', {'execute': execute, 'owner': trace['owner'], 'model_requests': 0,
             'source_refs': refs, 'snapshot_sha256': trace['snapshot']['digest'],
             'store': str(output / 'store'), 'expected_latest': None,
             'preparation': 'full_original_root_runtime_replay_included_in_elapsed_time',
             'code': [file_ref(ROOT / name) for name in (
                 'scripts/validate-recursive-paper-candidate.py', 'src/adapters/capability_motif_learning.py',
                 'src/adapters/capability_script_execution.py', 'scenarios/paper_proofreading/frontier/publish.mjs',
                 'scenarios/paper_proofreading/frontier/check.py', 'scenarios/paper_proofreading/frontier/oracle.py')]})
        result['boundary_projection'] = file_ref(output / 'boundary-projection.json')
        if execute:
            plan = {'owner': trace['owner'], 'store': str(output / 'store'),
                    'candidate': str(output / 'candidate.json'), 'expected_latest': None,
                    'output': str(output / 'publication')}
            for label, case in manifest['cases'].items():
                directory = output / ('prepare-' + label)
                tick = time.monotonic()
                preparation = {'label': label, 'status': 'failed', 'execution': None,
                               'model_requests': 0, 'total_cost_usd': None}
                result['preparation_runs'].append(preparation)
                try:
                    execute_script(trace['snapshot'], root, manifest['libraries'], case['inputs'],
                                   case['input'], directory, case['id'] + '-prepare')
                    execution_ref = file_ref(directory / 'trace.json')
                    observed = capture_composition_trace(trace['snapshot'], execution_ref=execution_ref,
                        task_input=case['input'], task_fingerprint=capability_digest(sorted(i['source']['sha256'] for i in case['inputs'])))
                    args, calls = prepare_arguments(proposal, observed)
                    save(directory / 'local-input.json', args)
                    save(directory / 'local-input-evidence.json', {'execution': execution_ref,
                         'runtime_call_ids': calls, 'projection': result['boundary_projection']})
                    preparation.update(status='succeeded', input=file_ref(directory / 'local-input.json'))
                finally:
                    preparation['elapsed_seconds'] = time.monotonic() - tick
                    if (directory / 'trace.json').exists():
                        preparation['execution'] = file_ref(directory / 'trace.json')
                original_manifest = read(file_ref(directory / 'manifest.json'))
                plan[label] = {'id': case['id'], 'workspace': original_manifest['workspace'],
                     'input': args, 'specification': case['specification'],
                     'manifest': {'format': 'script_capability_task_v1', 'libraries': manifest['libraries'],
                                  'inputs': original_manifest['inputs']}}
            for ref in refs:
                evidence(ref)
            save(output / 'publication-plan.json', plan)
            with (output / 'publication-stdout.log').open('x') as stdout, (output / 'publication-stderr.log').open('x') as stderr:
                returncode = run_child(['node', str(ROOT / 'scenarios/paper_proofreading/frontier/publish.mjs'),
                     str(output / 'publication-plan.json')], cwd=ROOT,
                     env={**os.environ, 'SSS_PYTHON': sys.executable}, stdout=stdout, stderr=stderr)
            publication = output / 'publication/result.json'
            verdict = read(file_ref(publication)) if publication.exists() else {}
            result['publication_result'] = file_ref(publication) if publication.exists() else None
            if returncode or verdict.get('status') != 'completed' or verdict.get('followup_passed') is not True:
                raise ValueError('paper_recursive_publication_or_followup_failed')
            for ref in refs:
                evidence(ref)
            result.update(status='completed', quality='independent_frontier_oracle_passed',
                publication_sha256=verdict['publication_sha256'],
                actual_published_call=file_ref(output / 'publication/followup/trace.json'),
                validation_quality=file_ref(output / 'publication/validation/validation.json'),
                followup_quality=file_ref(output / 'publication/followup/validation.json'))
        result['elapsed_seconds'] = time.monotonic() - started
        save(output / 'result.json', result)
        return result
    except BaseException as error:
        result.update(status='interrupted' if isinstance(error, (KeyboardInterrupt, SystemExit)) else 'failed',
                      error=type(error).__name__ + ':' + str(error), elapsed_seconds=time.monotonic() - started)
        result['publication_evidence'] = {name: file_ref(output / 'publication' / name)
            for name in ('result.json', 'publication.json', 'validation/trace.json', 'validation/validation.json',
                         'followup/trace.json', 'followup/validation.json')
            if (output / 'publication' / name).is_file()}
        result['published_before_failure'] = (output / 'publication/publication.json').is_file()
        save(output / 'result.json', result)
        raise


def main():
    def interrupted(signum, frame):
        raise KeyboardInterrupt('paper_recursive_interrupted')
    signal.signal(signal.SIGTERM, interrupted)
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--manifest', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--execute', action='store_true')
    args = parser.parse_args()
    print(json.dumps(run_manifest(read(file_ref(args.manifest)), args.output, execute=args.execute), ensure_ascii=False))


if __name__ == '__main__':
    main()
