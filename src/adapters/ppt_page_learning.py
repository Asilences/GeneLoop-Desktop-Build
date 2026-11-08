"""Background parameterization of repeated, delivered normal-task pages."""
from pathlib import Path
import os
import subprocess
from datetime import datetime, timezone

from .ppt_component_learning import fixed_file, propose_component, prepare_candidate, decode_component_proposal, proposal_request, TEXT_CONTENT_POLICY


def cached_page_proposal(store, sources):
    from .ppt_program_learning import read, digest, sha
    versions = [row['svg_sha256'] for row in sources]
    models = [*sorted(store.glob('program-*/model-repair')), *sorted(store.glob('program-*/model-proposal'))]
    for model in models:
        folder = model.parent
        if folder.is_symlink() or model.is_symlink():
            continue
        evidence = folder / 'learning-evidence.json'
        answer = model / 'response.json'
        proposal = model / 'proposal.json'
        request = model / 'request.json'
        if not all(path.is_file() and not path.is_symlink() for path in (evidence, answer, proposal, request)):
            continue
        try:
            if [row['svg_sha256'] for row in read(evidence)['sources']] != versions:
                continue
            cached_request = read(request)
            witness = {'parameter_policy': TEXT_CONTENT_POLICY}
            if model.name == 'model-repair':
                witness['certification_findings'] = True
            if cached_request.get('messages', [])[:1] != proposal_request(witness, independent={})['messages'][:1]:
                continue
            json_object = cached_request.get('response_format') == {'type': 'json_object'}
            value = decode_component_proposal(read(answer), independent=True, allow_json_object=json_object, text_content_only=True)
            if digest(value) != digest(read(proposal)):
                continue
        except (ValueError, KeyError, OSError, TypeError):
            continue
        return value, {'response': str(answer), 'response_sha256': sha(answer), 'proposal': str(proposal),
                       'proposal_sha256': sha(proposal), 'request': str(request), 'request_sha256': sha(request)}
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
    selected = store / 'program-selected.json'
    if selected.exists():
        pointer = read(selected)
        if pointer.get('phase') in ('probation', 'active') and len(read(store / pointer['library'])['programs']) >= 16:
            save(status_path, {'status': 'library_protocol_capacity_reached', 'model_request_attempted': False})
            return False
    for a, b in pairs:
        opportunity = digest({'layouts': sorted([a.get('layout_fingerprint', a.get('layout_family', 'unknown')),
                                                 b.get('layout_fingerprint', b.get('layout_family', 'unknown'))]),
                              'implementation': implementation})
        if any(row.get('opportunity') == opportunity and row['status'] in ('certified_probation', 'certified_candidate_retained') for row in attempts.values()):
            continue
        identity = digest({'sources': [a['svg_sha256'], b['svg_sha256']], 'implementation': implementation})
        previous = attempts.get(identity)
        folder = store / ('program-' + identity[:24])
        if previous and previous['status'] not in ('started', 'retryable'):
            continue
        if previous and (folder / 'model-proposal/request.json').exists() and not (folder / 'model-proposal/response.json').exists():
            previous['status'] = 'awaiting_request_reconciliation'
            save(attempts_path, attempts)
            save(status_path, {'status': 'awaiting_request_reconciliation', 'model_request_attempted': False,
                               'reason': 'Original request has no recoverable response; its charge must be reconciled before resending.'})
            continue
        attempts[identity] = {**(previous or {}), 'status': 'started', 'opportunity': opportunity,
                              'training_task': a['task_id'], 'independent_task': b['task_id'],
                              'updated_at': datetime.now(timezone.utc).isoformat()}
        save(attempts_path, attempts)
        folder.mkdir(exist_ok=True, mode=0o700)
        locks = {}
        repair_attempted = False
        try:
            witnesses = []
            for row in (a, b):
                raw = fixed_file(row['svg'], row['svg_sha256'], max_bytes=100_000).read_text()
                proof = row['delivered']
                receipt = fixed_file(proof['receipt'], proof['receipt_sha256'])
                locks[Path(row['svg']).relative_to(output).as_posix()] = row['svg_sha256']
                locks[receipt.relative_to(output).as_posix()] = proof['receipt_sha256']
                witnesses.append({'task_id': row['task_id'], 'source': raw, 'source_sha256': row['svg_sha256'],
                                  'parameter_policy': TEXT_CONTENT_POLICY,
                                  'events_sha256': row['events_sha256'], 'call_id': row['call_id'],
                                  'quality_scope': infos[row['task_id']][1].get('page_learning_scope', 'normal_delivery_mechanical_checks_scientific_and_visual_quality_unknown'),
                                  'source_quality': infos[row['task_id']][1].get('page_quality'), 'delivered': proof})
            scopes = {infos[row['task_id']][0]['id']: infos[row['task_id']][1].get('page_learning_scope') for row in (a, b)}
            save(folder / 'learning-evidence.json', {'sources': [a, b], 'implementation': implementation, 'support_scopes': scopes})
            proposal, reused = cached_page_proposal(store, (a, b))
            if proposal is None:
                proposal = propose_component(witnesses[0], policy, folder / 'model-proposal', independent=witnesses[1])
            else:
                save(folder / 'proposal-reuse.json', reused)
                locks[(folder / 'proposal-reuse.json').relative_to(output).as_posix()] = sha(folder / 'proposal-reuse.json')
                for name in ('request', 'response', 'proposal'):
                    locks[Path(reused[name]).relative_to(output).as_posix()] = reused[name + '_sha256']
            heldout = proposal.pop('heldout_parameters')
            if not (folder / 'candidate/candidates.json').exists():
                prepare_candidate(witnesses[0], proposal, folder / 'candidate', {'task_id': b['task_id'], 'parameters': heldout})
            result = certify_programs(folder / 'candidate/candidates.json', folder / 'candidate', request.get('command_resources') or {})
            save(folder / 'certification-run.json', {'exit_code': result.returncode, 'stdout': result.stdout[-8000:], 'stderr': result.stderr[-8000:]})
            path = folder / 'candidate/library.json'
            report = folder / 'candidate/report.json'
            if not result.returncode and path.is_file() and not read(path).get('programs') and report.is_file() and read(report).get('rejected'):
                repair = folder / 'model-repair'
                correction = {**witnesses[0], 'rejected_proposal': {**proposal, 'heldout_parameters': heldout},
                              'certification_findings': read(report)}
                repair_request = proposal_request(correction, independent=witnesses[1])
                if repair.exists():
                    if not (repair / 'response.json').is_file():
                        raise ValueError('page_repair_awaiting_request_reconciliation')
                    if read(repair / 'request.json') != repair_request:
                        raise ValueError('page_repair_request_changed')
                    proposal = decode_component_proposal(read(repair / 'response.json'), independent=True, allow_json_object=True, text_content_only=True)
                    if digest(proposal) != digest(read(repair / 'proposal.json')):
                        raise ValueError('page_repair_proposal_changed')
                else:
                    repair_attempted = True
                    proposal = propose_component(correction, policy, repair, independent=witnesses[1])
                heldout = proposal.pop('heldout_parameters')
                candidate = folder / 'candidate-repair'
                if not (candidate / 'candidates.json').exists():
                    prepare_candidate(witnesses[0], proposal, candidate, {'task_id': b['task_id'], 'parameters': heldout})
                result = certify_programs(candidate / 'candidates.json', candidate, request.get('command_resources') or {})
                save(folder / 'repair-certification-run.json', {'exit_code': result.returncode, 'stdout': result.stdout[-8000:], 'stderr': result.stderr[-8000:]})
                for evidence in [report, *(repair / name for name in ('request.json', 'response.json', 'proposal.json'))]:
                    locks[evidence.relative_to(output).as_posix()] = sha(evidence)
                path = candidate / 'library.json'
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
            from .ppt_program_evaluation import publish_generation
            published = publish_generation(output, store, request, folder, library, locks,
                [infos[row['task_id']][0]['id'] for row in (a, b)],
                {key: [infos[row['task_id']][1][key] for row in (a, b)] for key in ('decision_id', 'source_signature', 'question_sha256')},
                'automatic_normal_page_parameterization_v1', support_scopes=scopes)
            attempts[identity]['status'] = 'certified_probation' if published else 'certified_candidate_retained'
            save(attempts_path, attempts)
            save(status_path, {'status': attempts[identity]['status'], 'library_digest': library['digest'],
                               'model_request_attempted': reused is None or repair_attempted, 'proposal_reused': reused is not None,
                               'model_repair_attempted': repair_attempted, 'learning_cost_in_execution': False})
            return published
        except Exception as error:
            retryable = isinstance(error, (OSError, ConnectionError, subprocess.TimeoutExpired))
            attempts[identity].update(status='retryable' if retryable else 'rejected', reason=str(error)[:300])
            save(attempts_path, attempts)
            save(status_path, {'status': attempts[identity]['status'], 'reason': str(error)[:300], 'model_request_attempted': (folder / 'model-proposal/request.json').is_file(), 'learning_cost_in_execution': False})
            return False
    save(status_path, {'status': 'unchanged_evidence_no_model_request'})
    return False
