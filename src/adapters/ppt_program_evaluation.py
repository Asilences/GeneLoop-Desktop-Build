"""Separate certified-program availability from subsequent use and cost evidence."""
from pathlib import Path
import json


def generation_groups(pointer, programs=None):
    if pointer.get('groups'):
        return pointer['groups']
    return [{'id': pointer['library_digest'], 'program_ids': [p['id'] for p in programs] if programs is not None else pointer['added_program_ids'],
             'support_turns': pointer['support_turns'], 'support': pointer['support'],
             'evidence_locks': pointer['evidence_locks'], 'phase': pointer['phase']}]


def publish_generation(output, store, request, folder, library, locks, support_turns, support, origin, *, support_scopes=None):
    from .ppt_program_learning import read, save, sha, digest, checked, program_implementation_signature, LAYOUT_ONLY_SCOPE
    selected = store / 'program-selected.json'
    previous = read(selected) if selected.exists() else None
    if previous and previous.get('phase') not in ('probation', 'active'):
        previous = None
    groups, programs = [], []
    if previous:
        if previous['user'] != request['user'] or previous['scope'] != request['scope']:
            raise ValueError('foreign PPT program generation')
        if previous.get('implementation_signature') != program_implementation_signature():
            raise ValueError('PPT program implementation changed; fresh certification required')
        old_path = checked(output, (store / previous['library']).relative_to(output), previous['library_sha256'])
        old = read(old_path)
        programs = old['programs']
        groups = generation_groups(previous, programs)
        for name, version in old.get('code_locks', {}).items():
            if library.get('code_locks', {}).get(name) != version:
                raise ValueError('PPT program generations have incompatible code locks')
    known = {row['id'] for row in programs}
    added = [row for row in library['programs'] if row['id'] not in known]
    if not added:
        return False
    if LAYOUT_ONLY_SCOPE in (support_scopes or {}).values() and any(not row.get('component') for row in added):
        raise ValueError('Layout-only evidence requires certified parameterized page components')
    if len(programs) + len(added) > 16:
        save(folder / 'capacity.json', {'status': 'certified_candidate_retained', 'reason': 'library_protocol_capacity_reached'})
        return False
    group = {'id': library['digest'], 'program_ids': [row['id'] for row in added],
             'support_turns': support_turns, 'support': support, 'evidence_locks': locks, 'phase': 'probation',
             'support_scopes': support_scopes or {}}
    groups = [*groups, group]
    body = {k: v for k, v in library.items() if k != 'digest'}
    body['programs'] = [*programs, *added]
    if previous:
        body['parent_digest'] = previous['library_digest']
    merged = {**body, 'digest': digest(body)}
    save(folder / 'library.json', merged)
    feedback = store / 'feedback-version.json'
    pointer = {'schema_version': 1, 'user': request['user'], 'scope': request['scope'], 'phase': 'probation',
               'origin': origin, 'implementation_signature': program_implementation_signature(),
               'library': (folder / 'library.json').relative_to(store).as_posix(),
               'library_sha256': sha(folder / 'library.json'), 'library_digest': merged['digest'],
               'added_program_ids': [row['id'] for row in added], 'groups': groups,
               'feedback_version': sha(feedback) if feedback.exists() else None,
               'evidence_locks': {n: h for g in groups for n, h in g['evidence_locks'].items()},
               'support_turns': list(dict.fromkeys(t for g in groups for t in g['support_turns'])),
               'support': {key: list(dict.fromkeys(v for g in groups for v in g['support'][key])) for key in support}}
    save(selected, pointer)
    (store / 'program-suspended.json').unlink(missing_ok=True)
    return True


def evaluate_generation(output, store, request, pointer, infos, turns, reviewed, *, delivery, positive, costs):
    from .ppt_program_learning import ROOT, checked, digest, read, save, sha, program_implementation_signature, LAYOUT_ONLY_SCOPE
    if pointer['user'] != request['user'] or pointer['scope'] != request['scope']:
        raise ValueError('foreign PPT program generation')
    if pointer.get('implementation_signature') != program_implementation_signature():
        raise ValueError('PPT program implementation changed; fresh certification required')
    library_path = checked(output, (store / pointer['library']).relative_to(output), pointer['library_sha256'])
    library = read(library_path)
    if any(sha(ROOT / name) != version for name, version in library.get('code_locks', {}).items()):
        raise ValueError('PPT program execution code changed')
    component_ids = {p['id'] for p in library['programs'] if p.get('component')}
    groups, all_pairs, all_uses, rejected = [], {}, [], []
    identity_keys = ('decision_id', 'source_signature', 'question_sha256')
    suspended_groups = []
    for original in generation_groups(pointer, library['programs']):
        group = dict(original)
        layout_only = (LAYOUT_ONLY_SCOPE in group.get('support_scopes', {}).values() and
                       bool(group['program_ids']) and set(group['program_ids']).issubset(component_ids))
        blocked, pending, pairs, uses, seen = [], [], [], [], set()
        try:
            for name, version in group['evidence_locks'].items():
                checked(output, name, version)
            for ref in group['support_turns']:
                turn = turns.get(ref)
                lane = turn.get('learning_lane', 'baseline') if turn else 'baseline'
                if not turn or not positive(reviewed.get((ref, lane)), turn, lane):
                    raise ValueError('PPT program supporting feedback withdrawn')
                source_info = infos.get(turn.get('lanes', {}).get(lane, {}).get('task_id'))
                if source_info:
                    quality = delivery(output, turn, lane, {}, store=store, info=source_info, review=reviewed.get((ref, lane)))
                    layout_support = group.get('support_scopes', {}).get(ref) == LAYOUT_ONLY_SCOPE and quality.get('layout_status') == 'passed'
                    if not layout_support and (quality.get('status') == 'failed' or quality.get('model_failed_pages')):
                        raise ValueError('PPT program supporting quality failed')
        except (ValueError, KeyError, OSError, TypeError) as error:
            blocked.append({'id': group['id'], 'reason': str(error)[:200]})
        for turn in turns.values():
            if turn.get('status') not in ('completed', 'failed', 'cancelled'):
                continue
            single = turn.get('presentation') == 'single'
            lane = turn.get('learning_lane', 'motif') if single else 'motif'
            task_id = turn.get('lanes', {}).get(lane, {}).get('task_id')
            if not task_id:
                continue
            task_dir = output / 'tasks' / task_id
            snapshot, audit = task_dir / 'ppt-program-snapshot.json', task_dir / 'artifact-motif-audit.jsonl'
            if not snapshot.is_file() or not audit.is_file():
                continue
            checked(output, snapshot.relative_to(output))
            checked(output, audit.relative_to(output))
            snap = read(snapshot)
            if snap.get('user') not in (None, request['user']) or snap.get('scope') not in (None, request['scope']):
                raise ValueError('foreign program task snapshot')
            admitted = {snap.get('library_digest'), *(g['id'] for g in snap.get('groups', []))}
            if pointer['library_digest'] not in admitted and group['id'] not in admitted:
                continue
            rows = [json.loads(line) for line in audit.read_text(encoding='utf-8').splitlines() if line]
            used = [row for row in rows if row.get('program_id') in group['program_ids'] and row.get('kind') ==
                    ('component_used_in_delivery' if row.get('program_id') in component_ids else 'artifact_program_verified')]
            if not used:
                continue
            info = infos.get(task_id)
            if not info:
                pending.append({'id': turn['id'], 'reason': 'program_candidate_accounting_incomplete'})
                continue
            identity = tuple(info[k] for k in ('decision_id', 'source_signature', 'question_sha256'))
            if any(value in group['support'][key] for key, value in zip(identity_keys, identity)) or any((key, value) in seen for key, value in zip(identity_keys, identity)):
                continue
            if info['effective'].get('mode') != 'execute' or info['state'].get('status') != 'completed':
                pending.append({'id': turn['id'], 'reason': 'program_use_not_completed'})
                continue
            if not positive(reviewed.get((turn['id'], lane)), turn, lane):
                blocked.append({'id': turn['id'], 'reason': 'program_negative_feedback'})
                continue
            locks = dict(info['locks'])
            proof = delivery(output, turn, lane, locks, store=store, info=info, review=reviewed.get((turn['id'], lane)))
            if proof.get('status') == 'failed' or proof.get('model_failed_pages'):
                used_pages = {row.get('page') for row in used if row.get('page') is not None}
                failed_pages = set(proof.get('model_failed_pages', []))
                item = {'id': turn['id'], 'reason': 'program_delivery_quality_failed', 'failed_pages': sorted(failed_pages)}
                if layout_only and proof.get('layout_status') == 'passed':
                    # This generation was never a certified source of facts.
                    # Retain only its already-certified layout scope. The bad
                    # task is excluded from uses, promotion and cost evidence.
                    pending.append({**item, 'reason': 'semantic_quality_failed_layout_scope_retained',
                                    'quality_record': proof, 'qualifying_use': False})
                    continue
                if used_pages.intersection(failed_pages):
                    blocked.append(item)
                else:
                    pending.append(item)
                continue
            locks[audit.relative_to(output).as_posix()] = sha(audit)
            locks[snapshot.relative_to(output).as_posix()] = sha(snapshot)
            uses.append({'task_id': task_id, 'comparison_id': turn['id'], 'quality_record': proof,
                         'program_reuses': len(used), 'evidence_locks': locks,
                         'cost_advantage': 'unknown_without_matched_baseline' if single else 'evaluated_separately'})
            for key, value in zip(identity_keys, identity):
                seen.add((key, value))
            if single:
                continue
            base = infos.get(turn['lanes'].get('baseline', {}).get('task_id'))
            if not base or base['state'].get('status') != 'completed':
                pending.append({'id': turn['id'], 'reason': 'program_baseline_accounting_or_delivery_incomplete'})
                continue
            if (base['compatibility'] != info['compatibility'] or base['question_sha256'] != info['question_sha256'] or
                    base['source_signature'] != info['source_signature'] or base['effective'].get('mode') != 'baseline'):
                pending.append({'id': turn['id'], 'reason': 'program_non_matching_comparison'})
                continue
            if not positive(reviewed.get((turn['id'], 'baseline')), turn, 'baseline'):
                pending.append({'id': turn['id'], 'reason': 'program_baseline_negative_feedback'})
                continue
            locks.update(base['locks'])
            base_proof = delivery(output, turn, 'baseline', locks, store=store, info=base, review=reviewed.get((turn['id'], 'baseline')))
            if base_proof.get('status') == 'failed' or base_proof.get('model_failed_pages'):
                pending.append({'id': turn['id'], 'reason': 'program_baseline_quality_failed'})
                continue
            attempts = costs(turn, infos, locks)
            if attempts['motif']['proxy_usd'] >= attempts['baseline']['proxy_usd']:
                blocked.append({'id': turn['id'], 'reason': 'program_full_cost_regression'})
                continue
            br, op = reviewed.get((turn['id'], 'baseline')), reviewed.get((turn['id'], lane))
            if br and op and op['human_minutes'] > br['human_minutes']:
                blocked.append({'id': turn['id'], 'reason': 'program_human_revision_regression'})
                continue
            pair = {'comparison_id': turn['id'], 'attempts': attempts, 'quality_records': {'baseline': base_proof, 'motif': proof},
                    'program_reuses': len(used), 'verified_skips_attributed_to_program': 0, 'evidence_locks': locks}
            pairs.append(pair)
        group.update(uses=uses, pairs=pairs, pending=pending, blocked=blocked)
        if blocked:
            group['phase'] = 'suspended'
            rejected.extend(blocked)
            suspended_groups.append(group)
        else:
            group['phase'] = 'active' if len(pairs) >= 2 else 'retained' if len(uses) >= 2 else 'probation'
            groups.append(group)
            all_uses.extend(uses)
            all_pairs.update({pair['comparison_id']: pair for pair in pairs})
    if suspended_groups:
        retired_path = store / 'program-retired.json'
        retired = read(retired_path) if retired_path.exists() else []
        known = {row['generation'].get('id') for row in retired}
        retired.extend({'implementation': pointer['implementation_signature'], 'program_ids': group['program_ids'], 'generation': group}
                       for group in suspended_groups if group['id'] not in known)
        save(retired_path, retired)
    if not groups:
        pointer = {**pointer, 'phase': 'disabled', 'blocked': rejected, 'groups': []}
        save(store / 'program-selected.json', pointer)
        return pointer
    retained = {ident for group in groups for ident in group['program_ids']}
    programs = [row for row in library['programs'] if row['id'] in retained]
    if len(programs) != len(library['programs']):
        body = {k: v for k, v in library.items() if k != 'digest'}
        body.update(programs=programs, parent_digest=library['digest'])
        library = {**body, 'digest': digest(body)}
        folder = store / ('retained-' + library['digest'][:24])
        folder.mkdir(exist_ok=True, mode=0o700)
        library_path = folder / 'library.json'
        save(library_path, library)
    evaluation = {'pairs': list(all_pairs.values()), 'uses': all_uses, 'groups': groups, 'suspended': rejected,
                  'required_independent_pairs': 2, 'scope': 'independent use and mechanical quality; cost advantage requires matched comparisons',
                  'quality_cost_promoted': all(g['phase'] == 'active' for g in groups) and
                   all(q['status'] == 'passed' for p in all_pairs.values() for q in p['quality_records'].values())}
    evaluation_path = library_path.parent / 'evaluation.json'
    save(evaluation_path, evaluation)
    feedback = store / 'feedback-version.json'
    pointer = {**pointer, 'groups': groups, 'phase': 'active' if all(g['phase'] == 'active' for g in groups) else 'probation',
               'library': library_path.relative_to(store).as_posix(), 'library_sha256': sha(library_path), 'library_digest': library['digest'],
               'evaluation_sha256': sha(evaluation_path), 'quality_cost_promoted': evaluation['quality_cost_promoted'],
               'feedback_version': sha(feedback) if feedback.exists() else None,
               'support_turns': list(dict.fromkeys(t for g in groups for t in g['support_turns'])),
               'support': {key: list(dict.fromkeys(v for g in groups for v in g['support'][key])) for key in pointer['support']},
               'evidence_locks': {**{n: h for g in groups for n, h in g['evidence_locks'].items()},
                                  **{n: h for u in all_uses for n, h in u['evidence_locks'].items()},
                                  **{n: h for p in all_pairs.values() for n, h in p['evidence_locks'].items()}}}
    save(store / 'program-selected.json', pointer)
    return pointer
