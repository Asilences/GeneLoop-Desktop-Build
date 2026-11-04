"""Background parameterization of repeated, delivered normal-task pages."""
from pathlib import Path
import os

from .ppt_component_learning import fixed_file, propose_component, prepare_candidate, decode_component_proposal


def cached_page_proposal(store, sources):
    from .ppt_program_learning import read, digest, sha
    versions = [row['svg_sha256'] for row in sources]
    for folder in sorted(store.glob('program-*')):
        if folder.is_symlink():
            continue
        evidence = folder / 'learning-evidence.json'
        answer = folder / 'model-proposal/response.json'
        proposal = folder / 'model-proposal/proposal.json'
        if not all(path.is_file() and not path.is_symlink() for path in (evidence, answer, proposal)):
            continue
        try:
            if [row['svg_sha256'] for row in read(evidence)['sources']] != versions:
                continue
            value = decode_component_proposal(read(answer), independent=True)
            if digest(value) != digest(read(proposal)):
                continue
        except (ValueError, KeyError, OSError, TypeError):
            continue
        return value, {'response': str(answer), 'response_sha256': sha(answer), 'proposal': str(proposal), 'proposal_sha256': sha(proposal)}
    return None, None


def advance_page_components(output, store, request, eligible):
    from .ppt_program_learning import read, save, digest, sha, program_implementation_signature, certify_programs
    policy = os.environ.get('GENELOOP_PPT_COMPONENT_LEARNING_POLICY')
    if not policy:
        return False
    status_path = store / 'page-learning-status.json'
    index_path = store / 'component-opportunities/index.json'
    if not index_path.is_file():
        save(status_path, {'status': 'waiting_for_delivered_pages'})
        return False
    index = read(index_path)
    infos = {info['task_id']: (turn, info) for turn, info in eligible}
    sources = [row for row in index['sources'].values() if row.get('delivered') and row['task_id'] in infos]
    pairs = [(a, b) for a in sources for b in sources if a['task_id'] < b['task_id'] and
             a.get('source_signature') and a['source_signature'] != b.get('source_signature') and
             a.get('compatibility') == b.get('compatibility') and
             (a['layout_fingerprint'] == b['layout_fingerprint'] or
              (a.get('layout_family') and a['layout_family'] == b.get('layout_family')) or
              a['delivered'].get('deck_sha256') in b.get('input_versions', []) or
              b['delivered'].get('deck_sha256') in a.get('input_versions', [])) and
             all(infos[a['task_id']][1][key] != infos[b['task_id']][1][key] for key in ('decision_id', 'question_sha256'))]
    if not pairs:
        save(status_path, {'status': 'waiting_for_repeated_independent_layout', 'delivered_pages': len(sources)})
        return False
    implementation = program_implementation_signature()
    feedback = store / 'feedback-version.json'
    feedback_version = sha(feedback) if feedback.exists() else None
    attempts_path = store / 'page-learning-attempts.json'
    attempts = read(attempts_path) if attempts_path.exists() else {}
    for a, b in pairs:
        identity = digest({'sources': [a['svg_sha256'], b['svg_sha256']], 'implementation': implementation})
        if identity in attempts:
            continue
        attempts[identity] = {'status': 'started', 'training_task': a['task_id'], 'independent_task': b['task_id']}
        save(attempts_path, attempts)
        folder = store / ('program-' + identity[:24])
        folder.mkdir(mode=0o700)
        locks = {}
        try:
            witnesses = []
            for row in (a, b):
                raw = fixed_file(row['svg'], row['svg_sha256'], max_bytes=100_000).read_text()
                proof = row['delivered']
                receipt = fixed_file(proof['receipt'], proof['receipt_sha256'])
                locks[Path(row['svg']).relative_to(output).as_posix()] = row['svg_sha256']
                locks[receipt.relative_to(output).as_posix()] = proof['receipt_sha256']
                witnesses.append({'task_id': row['task_id'], 'source': raw, 'source_sha256': row['svg_sha256'],
                                  'events_sha256': row['events_sha256'], 'call_id': row['call_id'],
                                  'quality_scope': 'normal_delivery_mechanical_checks_scientific_and_visual_quality_unknown', 'delivered': proof})
            save(folder / 'learning-evidence.json', {'sources': [a, b], 'implementation': implementation})
            proposal, reused = cached_page_proposal(store, (a, b))
            if proposal is None:
                proposal = propose_component(witnesses[0], policy, folder / 'model-proposal', independent=witnesses[1])
            else:
                save(folder / 'proposal-reuse.json', reused)
                locks[(folder / 'proposal-reuse.json').relative_to(output).as_posix()] = sha(folder / 'proposal-reuse.json')
                for name in ('response', 'proposal'):
                    locks[Path(reused[name]).relative_to(output).as_posix()] = reused[name + '_sha256']
            heldout = proposal.pop('heldout_parameters')
            prepare_candidate(witnesses[0], proposal, folder / 'candidate', {'task_id': b['task_id'], 'parameters': heldout})
            result = certify_programs(folder / 'candidate/candidates.json', folder / 'candidate', request.get('command_resources') or {})
            save(folder / 'certification-run.json', {'exit_code': result.returncode, 'stdout': result.stdout[-8000:], 'stderr': result.stderr[-8000:]})
            path = folder / 'candidate/library.json'
            if result.returncode or not path.is_file() or not read(path).get('programs'):
                raise ValueError('automatic_page_independent_certification_rejected')
            library = read(path)
            save(folder / 'library.json', library)
            for row in (a, b):
                locks.update(infos[row['task_id']][1]['locks'])
                task = Path(infos[row['task_id']][1]['task_dir'])
                for name in ('reuse-boundaries.jsonl', 'ppt-native-pages.jsonl'):
                    if (task / name).is_file():
                        locks[(task / name).relative_to(output).as_posix()] = sha(task / name)
            locks[(folder / 'learning-evidence.json').relative_to(output).as_posix()] = sha(folder / 'learning-evidence.json')
            if (sha(feedback) if feedback.exists() else None) != feedback_version:
                raise ValueError('page_learning_feedback_changed_during_generation')
            save(store / 'program-selected.json', {'schema_version': 1, 'user': request['user'], 'scope': request['scope'],
                 'phase': 'probation', 'origin': 'automatic_normal_page_parameterization_v1', 'implementation_signature': implementation,
                 'library': (folder / 'library.json').relative_to(store).as_posix(), 'library_sha256': sha(folder / 'library.json'),
                 'library_digest': library['digest'], 'added_program_ids': [p['id'] for p in library['programs']],
                 'feedback_version': feedback_version, 'evidence_locks': locks,
                 'support_turns': [infos[row['task_id']][0]['id'] for row in (a, b)],
                 'support': {key: [infos[row['task_id']][1][key] for row in (a, b)] for key in ('decision_id', 'source_signature', 'question_sha256')}})
            (store / 'program-suspended.json').unlink(missing_ok=True)
            attempts[identity]['status'] = 'certified_probation'
            save(attempts_path, attempts)
            save(status_path, {'status': 'certified_probation', 'library_digest': library['digest'],
                               'model_request_attempted': reused is None, 'proposal_reused': reused is not None, 'learning_cost_in_execution': False})
            return True
        except Exception as error:
            attempts[identity].update(status='rejected', reason=str(error)[:300])
            save(attempts_path, attempts)
            save(status_path, {'status': 'rejected', 'reason': str(error)[:300], 'model_request_attempted': (folder / 'model-proposal/request.json').is_file(), 'learning_cost_in_execution': False})
            return False
    save(status_path, {'status': 'unchanged_evidence_no_model_request'})
    return False
