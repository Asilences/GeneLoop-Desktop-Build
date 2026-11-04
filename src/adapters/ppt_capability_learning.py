"""Account-local bridge from normal PPT learning to the shared Capability pool."""
import json
import hashlib
import os
from pathlib import Path
import subprocess

from .capability_contract import capability_digest
from .capability_feedback import CapabilityFeedback
from .capability_materials import CapabilityMaterials
from .capability_scene import reference, load_scene_adapter
from .capability_improvement import run_improvement, evidence
from .ppt_program_learning import ROOT, read, save, checked, sha


def sync_ppt_capabilities(output, store, request, infos, turns, reviewed, *, delivery, positive):
    """Called under the existing learning lock; no model call unless host opted in.

    The normal program certifier stays authoritative. Public adoption adds no
    scientific-quality or savings claim and cannot bypass account withdrawal.
    """
    directory = store / 'capability'
    directory.mkdir(exist_ok=True, mode=0o700)
    observations = directory / 'observations'
    observations.mkdir(exist_ok=True, mode=0o700)
    eligible_refs = []
    for turn in turns.values():
        lane = turn.get('learning_lane', 'baseline')
        info = infos.get(turn.get('lanes', {}).get(lane, {}).get('task_id'))
        if (not info or info['state'].get('status') != 'completed' or info['state'].get('failure') or
                info['request'].get('role') in ('holdout', 'evaluate', 'benchmark') or
                info['request'].get('learning_eligible') is False or not positive(reviewed.get((turn['id'], lane)), turn, lane)):
            continue
        try:
            locks = dict(info['locks'])
            delivery(output, turn, lane, locks)
            refs = [reference(checked(output, name, version)) for name, version in sorted(locks.items())]
            events = read_events(Path(info['task_dir']) / 'events.jsonl')
            row = {'format': 'ppt_capability_observation_v1', 'owner': request['user'], 'scope': request['scope'],
                   'task_id': info['task_id'], 'status': 'passed',
                   'task_fingerprint': capability_digest([info['decision_id'], info['source_signature']]),
                   'evidence': refs, 'quality': 'mechanical_delivery_scientific_and_visual_unknown',
                   'trace': {'task_id': info['task_id'], 'tool_sequence': events,
                             'dependencies': 'unknown_unless_native_receipt', 'benefit': None}}
            folder = observations / capability_digest(row)
            folder.mkdir(exist_ok=True, mode=0o700)
            target = folder / 'observation.json'
            if not target.exists():
                save(target, row)
            eligible_refs.append(reference(target))
        except (OSError, ValueError, KeyError, TypeError):
            continue
    pointer_path = store / 'program-selected.json'
    if not pointer_path.exists() or (store / 'program-suspended.json').exists():
        withdraw_public_selection(directory, request['user'], {'reason': 'native_candidate_unavailable'})
        save(directory / 'status.json', {'status': 'waiting_for_native_certification', 'observations': eligible_refs})
        return
    pointer = read(pointer_path)
    if (pointer.get('user') != request['user'] or pointer.get('scope') != request['scope'] or
            pointer.get('phase') not in ('probation', 'active')):
        withdraw_public_selection(directory, request['user'], {'reason': 'native_candidate_unavailable', 'phase': pointer.get('phase')})
        save(directory / 'status.json', {'status': 'native_candidate_unavailable', 'observations': eligible_refs})
        return
    feedback_file = store / 'feedback-version.json'
    if pointer.get('feedback_version') != (sha(feedback_file) if feedback_file.exists() else None):
        raise ValueError('ppt_capability_feedback_changed')
    library = checked(output, (store / pointer['library']).relative_to(output), pointer['library_sha256'])
    refs = [reference(checked(output, name, version)) for name, version in sorted(pointer['evidence_locks'].items())]
    catalog = artifact_catalog(library, request['user'], pointer['library_sha256'])
    if not catalog['capabilities']:
        raise ValueError('ppt_capability_no_native_material')
    previous = directory / 'selected.json'
    if previous.exists() and read(previous).get('native_library_sha256') != pointer['library_sha256']:
        withdraw_public_selection(directory, request['user'], {'reason': 'native_generation_changed', 'library_sha256': pointer['library_sha256']})
    # Freeze admission, never reference a pointer which promotion may overwrite.
    admission = directory / ('admission-' + capability_digest(pointer) + '.json')
    if not admission.exists():
        save(admission, pointer)
    pool = CapabilityMaterials(directory / 'store/materials', request['user'])
    pool.register(backend='artifact_motif', library=reference(library), refs=[reference(admission), *refs],
                  acquisition_key=pointer['library_digest'], opportunity='ppt-normal-program-learning')
    seed = directory / ('seed-' + catalog['snapshot']['digest'] + '.json')
    seed_catalog = directory / ('seed-catalog-' + catalog['snapshot']['digest'] + '.json')
    if not seed.exists():
        save(seed, catalog['snapshot'])
    if not seed_catalog.exists():
        save(seed_catalog, catalog)
    plan_path = os.environ.get('GENELOOP_PPT_CAPABILITY_PLAN')
    outcome = 'material_registered'
    if plan_path:
        plan = read(Path(plan_path))
        if (plan.get('owner') != request['user'] or Path(plan['store']).resolve() != (directory / 'store').resolve() or
                plan.get('scene_adapter') != reference(ROOT / 'scenarios/ppt_master/capability_adapter.py')):
            raise ValueError('ppt_capability_host_plan_binding_invalid')
        # One public construction per native generation and frozen host plan,
        # rather than another paid proposal after every ordinary conversation.
        generation = capability_digest({'library': pointer['library_digest'], 'host_plan': reference(Path(plan_path))})
        plan.update(id='ppt-public-' + generation[:24], seed=reference(seed), seed_catalog=reference(seed_catalog),
                    output=str(directory / 'improvements' / generation))
        Path(plan['output']).parent.mkdir(exist_ok=True, mode=0o700)
        contexts = {capability_digest(entry['context']): entry['context'] for entry in plan.get('discovery', [])}
        if len(contexts) == 1:
            context = next(iter(contexts.values()))
            plan['discovery'] = [{'run': str(Path(ref['path']).parent), 'kind': 'ppt_normal_task',
                                  'role': 'training', 'context': context} for ref in eligible_refs]
        if not Path(plan['output']).exists():
            run_improvement(plan, load_scene_adapter(plan), execute=True)
        outcome = 'public_controller_observed'
    index = directory / 'materials-index.json'
    current_materials = [row for row in pool.records() if row['library']['sha256'] == pointer['library_sha256']]
    save(index, {'owner': request['user'], 'materials': current_materials})
    result = subprocess.run(['node', '--experimental-strip-types', 'scripts/export-capability-construction-library.mjs',
                             str(directory / 'store'), str(seed), str(index)], cwd=ROOT,
                            capture_output=True, text=True, encoding='utf-8', check=True)
    value = CapabilityFeedback(directory / 'store/feedback', request['user']).project(json.loads(result.stdout))
    snapshot = value['snapshot']
    if snapshot is None:
        save(directory / 'status.json', {'status': 'all_capabilities_withdrawn', 'observations': eligible_refs})
        return
    snapshot_path = directory / ('snapshot-' + snapshot['digest'] + '.json')
    if not snapshot_path.exists():
        save(snapshot_path, snapshot)
    feedback = directory / 'store/feedback' / hashlib.sha256(request['user'].encode()).hexdigest() / 'feedback.json'
    if feedback.exists():
        refs.append(reference(feedback))
    save(directory / 'selected.json', {'owner': request['user'], 'scope': request['scope'], 'snapshot': reference(snapshot_path),
         'native_library_sha256': pointer['library_sha256'], 'native_library_digest': pointer['library_digest'],
         'evidence': [reference(admission), *refs], 'publication_head': value.get('head'),
         'roots': [root for root in snapshot['roots'] if next(c for c in snapshot['capabilities'] if c['id'] == root['id'])['implementation']['kind'] == 'composition']})
    save(directory / 'status.json', {'status': outcome, 'observations': eligible_refs, 'native_materials': len(pool.records()),
         'snapshot_sha256': snapshot['digest'], 'published_roots': len(read(directory / 'selected.json')['roots']),
         'model_construction_enabled': bool(plan_path), 'learning_cost_in_execution': False})


def artifact_catalog(library, owner, expected):
    result = subprocess.run(['node', '--experimental-strip-types', 'scripts/run-artifact-capability.mjs', '--catalog',
                             str(library), owner, expected], cwd=ROOT, capture_output=True, text=True, encoding='utf-8', check=True)
    return json.loads(result.stdout)


def read_events(path):
    return [row.get('data', {}).get('name') for row in map(json.loads, path.read_text(encoding='utf-8').splitlines())
            if row.get('type') == 'tool/call']


def withdraw_public_selection(directory, owner, reason):
    selected_path = directory / 'selected.json'
    if not selected_path.exists():
        return
    selected = read(selected_path)
    if selected.get('owner') != owner:
        raise ValueError('ppt_capability_withdrawal_owner_changed')
    snapshot = json.loads(evidence(selected['snapshot']))
    proof = directory / ('withdrawal-' + capability_digest(reason) + '.json')
    if not proof.exists():
        save(proof, reason)
    feedback = CapabilityFeedback(directory / 'store/feedback', owner)
    for root in snapshot['roots']:
        feedback.withdraw(root, 'ppt_native_learning_withdrawn', reference(proof))
    selected_path.unlink()
