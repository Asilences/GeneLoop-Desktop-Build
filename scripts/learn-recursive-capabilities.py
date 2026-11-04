#!/usr/bin/env python3
"""核验真实能力调用轨迹，并显式启用原 Motif 学习；默认预览，模型请求为零。"""
from __future__ import annotations

import argparse
import copy
import hashlib
import json
import platform
import signal
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from src.adapters.capability_contract import capability_digest, capability_ref, validate_capability_snapshot
from src.adapters.capability_evolution import evolve_abstraction, validate_evolution_request
from src.adapters.capability_feedback import CapabilityFeedback, file_ref, verify
from src.adapters.capability_improvement import save, validate
from src.adapters.capability_motif_learning import _checked, learn_capability_motifs

SOURCES = (
    'scripts/learn-recursive-capabilities.py',
    'src/adapters/capability_motif_learning.py', 'src/adapters/capability_evolution.py',
    'src/adapters/capability_feedback.py', 'src/adapters/capability_builder.py',
    'src/adapters/capability_contract.py', 'src/adapters/dsh_trajectory.py',
    'src/motif_core/offline/trace_compiler.py', 'src/motif_core/offline/motif_miner.py',
    'schemas/capability-v1.schema.json',
)


def _read(ref):
    validate('evidence', ref)
    return json.loads(verify(ref))


def _preflight(manifest):
    if (not isinstance(manifest, dict) or set(manifest) - {'snapshot', 'training', 'heldout', 'evolution'}
            or not {'snapshot', 'training', 'heldout'} <= set(manifest)):
        raise ValueError('recursive_learning_manifest_invalid')
    if (not isinstance(manifest['training'], list) or len(manifest['training']) < 2
            or not isinstance(manifest['heldout'], list) or not manifest['heldout']):
        raise ValueError('recursive_learning_independent_tasks_required')
    snapshot = validate_capability_snapshot(_read(manifest['snapshot']))
    training = [_checked(_read(ref), snapshot['owner']) for ref in manifest['training']]
    heldout = [_checked(_read(ref), snapshot['owner']) for ref in manifest['heldout']]
    traces = [*training, *heldout]
    if (len({trace['task_id'] for trace in traces}) != len(traces)
            or len({trace['task_fingerprint'] for trace in traces}) != len(traces)):
        raise ValueError('recursive_learning_independent_tasks_required')
    if any(step['capability'] not in snapshot['roots'] for trace in traces for step in trace['steps']):
        raise ValueError('recursive_learning_dependency_changed')
    refs = [manifest['snapshot'], *manifest['training'], *manifest['heldout']]
    refs += [ref for trace in traces for ref in trace['evidence']]
    evolution = None
    if 'evolution' in manifest:
        spec = manifest['evolution']
        if not isinstance(spec, dict) or set(spec) != {'feedback_directory', 'prior_candidate', 'proposal'}:
            raise ValueError('recursive_learning_evolution_invalid')
        validate('evidence', spec['prior_candidate'])
        proposal = _read(spec['proposal'])
        owner_dir = Path(spec['feedback_directory']).resolve() / hashlib.sha256(snapshot['owner'].encode()).hexdigest()
        # Preview must not create an empty feedback account as a side effect.
        if not (owner_dir / 'feedback.json').is_file():
            raise ValueError('recursive_learning_feedback_missing')
        feedback = CapabilityFeedback(spec['feedback_directory'], snapshot['owner'])
        validate_evolution_request(training, heldout, snapshot, feedback=feedback,
                                   prior_candidate=spec['prior_candidate'], proposal=proposal)
        refs += [spec['prior_candidate'], spec['proposal'], file_ref(feedback.path)]
        refs += [ref for fact in feedback.read()['facts'].values() for ref in fact['evidence']]
        evolution = {'feedback': feedback, 'prior_candidate': spec['prior_candidate'], 'proposal': proposal}
    return snapshot, training, heldout, evolution, refs


def run_manifest(manifest, output, *, execute=False, private_root=None, manifest_ref=None):
    """Public CLI operation; tests may provide a private temporary root.

    Outputs are original compiled candidates, never certified capabilities or
    published roots. Feed them to the existing host-owned improvement adapter.
    """
    private_root = (ROOT / '.local' if private_root is None else Path(private_root)).resolve()
    output = Path(output).resolve()
    if output == private_root or not output.is_relative_to(private_root):
        raise ValueError('recursive_learning_private_output_required')
    output.mkdir(mode=0o700, parents=True, exist_ok=False)
    manifest = copy.deepcopy(manifest)
    save(output / 'manifest.json', manifest)
    base = {'format': 'capability_recursive_learning_result_v1', 'model_requests': 0,
            'publication_authorized': False, 'measured_improvement': None,
            'budget_credit': None, 'candidates': []}
    try:
        if manifest_ref is not None and _read(manifest_ref) != manifest:
            raise ValueError('recursive_learning_manifest_changed')
        snapshot, training, heldout, evolution, refs = _preflight(manifest)
        if manifest_ref is not None:
            refs.append(manifest_ref)
        node = subprocess.run(['node', '--version'], check=True, capture_output=True, text=True).stdout.strip()
        effective = {'owner': snapshot['owner'], 'execute': execute,
                     'manifest_sha256': capability_digest(manifest), 'snapshot_sha256': snapshot['digest'],
                     'source_refs': refs, 'model_requests': 0,
                     'python': sys.version, 'node': node, 'platform': platform.platform(),
                     'code_sha256': {name: hashlib.sha256((ROOT / name).read_bytes()).hexdigest() for name in SOURCES}}
        save(output / 'effective.json', effective)
        if not execute:
            result = {**base, 'status': 'preview', 'owner': snapshot['owner'],
                      'training_count': len(training), 'heldout_count': len(heldout),
                      'evolution': evolution is not None, 'effective': file_ref(output / 'effective.json')}
        else:
            learned = (learn_capability_motifs(training, heldout, snapshot) if evolution is None else
                       evolve_abstraction(training, heldout, snapshot, **evolution,
                                          directory=output / 'evolution', enabled=True))
            for ref in refs:
                verify(ref)
            save(output / 'learning.json', learned)
            candidates = []
            for index, row in enumerate(learned['candidates']):
                directory = output / ('candidate-' + str(index).zfill(3))
                directory.mkdir(mode=0o700)
                cap = row['compiled']['capability']
                if cap['certification'] != 'candidate' or cap['lifecycle'] != 'build_only':
                    raise ValueError('recursive_learning_cannot_self_certify')
                artifact = {'capability': capability_ref(cap)}
                for name in ('proposal', 'compiled', 'provenance', 'motif', 'evolution'):
                    if name in row:
                        save(directory / (name + '.json'), row[name])
                        artifact[name] = file_ref(directory / (name + '.json'))
                candidate = {name: copy.deepcopy(row[name]) for name in ('proposal', 'compiled', 'provenance', 'evolution')
                             if name in row}
                save(directory / 'candidate.json', candidate)
                artifact['candidate_ref'] = file_ref(directory / 'candidate.json')
                candidates.append(artifact)
            result = {**base, 'status': 'completed' if candidates else 'deferred',
                      'owner': snapshot['owner'], 'candidates': candidates,
                      'learning': file_ref(output / 'learning.json'),
                      'effective': file_ref(output / 'effective.json'),
                      'rejected': learned.get('rejected', []),
                      'scope': 'offline_candidate_learning_requires_existing_independent_publication'}
        save(output / 'result.json', result)
        return result
    except BaseException as error:
        save(output / 'failure.json', {**base,
            'status': 'interrupted' if isinstance(error, (KeyboardInterrupt, SystemExit)) else 'failed',
            'error': type(error).__name__ + ':' + str(error)})
        raise


def main():
    def interrupted(signum, frame):
        raise KeyboardInterrupt('recursive_learning_interrupted')
    signal.signal(signal.SIGTERM, interrupted)
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--manifest', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--execute', action='store_true', help='执行无模型离线学习；仍不发布能力')
    args = parser.parse_args()
    reference = file_ref(args.manifest)
    result = run_manifest(_read(reference), args.output, execute=args.execute, manifest_ref=reference)
    print(json.dumps(result, ensure_ascii=False, allow_nan=False))


if __name__ == '__main__':
    main()
