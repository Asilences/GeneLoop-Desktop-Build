"""Discover bounded data-flow continuations from owned normal tool traces.

Contracts describe tool effects and typed output fields. Tool order and argument
bindings come from adjacent successful calls, never from a supplied workflow.
"""
from src.adapters.filesystem_paths import Path
import json
import re
import sys

from src.adapters.ppt.learning.ppt_program_learning import checked, digest, read, sha, save

ROOT = Path(__file__).resolve().parents[4]


def workflow_environment():
    files = read(ROOT / 'scenarios/ppt_master/workflow-contracts.json')['implementation_files']
    current = digest({'platform': sys.platform, 'code_locks': {name: sha(ROOT / name) for name in files}})
    policy = ROOT / 'config/rsi-privacy-code-compat.json'
    reviewed = read(policy).get('ppt_workflow_environment', {}) if policy.is_file() else {}
    return reviewed.get(current, current)


def retained_workflows(output, folder, selected, request, environment, feedback_version):
    """Carry forward a compatible publication only while its own evidence is valid."""
    name = selected.get('library')
    locks = selected.get('evidence_locks')
    version = selected.get('sha256')
    if (selected.get('phase') not in ('probation', 'active') or selected.get('user') != request['user'] or
            selected.get('scope') != request['scope'] or selected.get('environment_sha256') != environment or
            selected.get('feedback_version') != feedback_version or not isinstance(name, str) or
            not re.fullmatch(r'[a-f0-9]{64}\.json', name) or not isinstance(version, str) or
            not re.fullmatch(r'[a-f0-9]{64}', version) or not isinstance(locks, dict) or not locks or
            any(not isinstance(value, str) or not re.fullmatch(r'[a-f0-9]{64}', value) for value in locks.values())):
        return {}, {}
    try:
        library = read(checked(folder, name, version))
        claimed = library.pop('digest')
        rows = library['programs']
        if (name != claimed + '.json' or digest(library) != claimed or library['version'] != 1 or
                library['kind'] != 'trace_learned_tool_continuations' or library['environment_sha256'] != environment or
                not isinstance(rows, list) or not 1 <= len(rows) <= 16):
            return {}, {}
        programs = {row['id']: row for row in rows if row['status'] == 'certified' and row['certification']['status'] == 'passed'}
        if len(programs) != len(rows):
            return {}, {}
        for path, version in locks.items():
            checked(output, path, version)
    except (ValueError, KeyError, OSError, TypeError, AttributeError):
        return {}, {}
    return programs, locks


def value_at(value, path):
    for part in path:
        value = value[part]
    return value


def tool_value(blocks, required_paths=()):
    values = []
    for block in blocks:
        if block.get('type') != 'text':
            continue
        try:
            value = json.loads(block['text'])
            if not isinstance(value, dict):
                continue
            for path in required_paths:
                value_at(value, path)
            values.append(value)
        except (ValueError, TypeError, KeyError, IndexError):
            continue
    # A nested image caption is not the native receipt. Multiple matching
    # receipts remain ambiguous; never choose one by position or substring.
    return values[0] if len(values) == 1 else None


def collect_workflow_trace(info):
    request, state = info['request'], info['state']
    if (request.get('learning_eligible') is False or request.get('role') in ('holdout', 'evaluate', 'benchmark') or
            state.get('status') != 'completed' or state.get('failure')):
        return None
    path = Path(info['task_dir']) / 'events.jsonl'
    calls, records = {}, []
    contracts = read(ROOT / 'scenarios/ppt_master/workflow-contracts.json')['tools']
    lines = path.read_text(encoding='utf-8').splitlines()
    start = info.get('effective', {}).get('trace_start_index', 0)
    if type(start) is not int or not 0 <= start <= len(lines):
        raise ValueError('ppt_workflow_trace_start_invalid')
    for sequence, line in enumerate(lines[start:], start=start):
        event = json.loads(line)
        data = event.get('data', {})
        if event.get('type') == 'tool/call':
            arguments = data['arguments']
            call = {'call_id': data['callId'], 'name': data['name'], 'call_sequence': sequence,
                'arguments': json.loads(arguments) if isinstance(arguments, str) else arguments,
                'error': True, 'content': [], 'value': None}
            calls[data['callId']] = call
            records.append(call)
        if event.get('type') == 'tool/result':
            for block in data.get('message', {}).get('content', []):
                call = calls.pop(block.get('toolCallId'), None)
                if block.get('type') == 'tool-result' and call:
                    contract=contracts.get(call['name'],{})
                    completion=contract.get('observed_completion')
                    paths=([completion[k] for k in ('success','empty_findings','collection')] if completion else
                           [contract['page_write']['version_output']] if contract.get('page_write') else [])
                    call.update(error=bool(block.get('isError')), content=block.get('content', []),
                                value=tool_value(block.get('content', []),paths), result_sequence=sequence)
    boundaries=Path(info['task_dir'])/'reuse-boundaries.jsonl'
    if boundaries.is_file():
        rows=[json.loads(line) for line in boundaries.read_text(encoding='utf-8').splitlines() if line]
        by_id={row['call_id']:row for row in rows}
        if len(by_id)==len(rows):
            for call in records:
                proof=by_id.get(call['call_id'])
                if proof and proof.get('tool')==call['name'] and proof.get('arguments_sha256')==digest(call['arguments']) and not proof.get('is_error'):
                    call['state_boundary']=proof
            info.setdefault('locks',{})[boundaries.relative_to(Path(info['task_dir']).parents[1]).as_posix()]=sha(boundaries)
    for call in records:
        value=call.get('value') or {}
        delivery_id=value.get('delivery_id')
        if not contracts.get(call['name'],{}).get('observed_completion') or not isinstance(delivery_id,str) or not 1<=len(delivery_id)<=128:
            continue
        matches=[]
        for candidate in (Path(info['task_dir'])/'ppt-delivery-receipts').glob('*.json'):
            if candidate.is_symlink() or len(candidate.stem)!=64 or any(c not in '0123456789abcdef' for c in candidate.stem):
                continue
            proof=read(candidate)
            if (proof.get('key')==candidate.stem and proof.get('delivery_id')==delivery_id and
                    proof.get('project')==value.get('project') and proof.get('artifacts')==value.get('artifacts')):
                matches.append((candidate,proof))
        if len(matches)!=1:
            continue
        receipt,proof=matches[0]
        call['delivery_evidence']={'project':proof['project'],'files':proof['dependencies']['files'],
            'pages':proof.get('page_receipts',[]),'artifacts':proof.get('artifacts',[])}
        info.setdefault('locks',{})[receipt.relative_to(Path(info['task_dir']).parents[1]).as_posix()]=sha(receipt)
    primary_versions = sorted(row['version_sha256'] for row in info['effective'].get('scene_inputs', [])
                          if row.get('file', '').lower().endswith(('.pdf','.md','.txt','.docx','.csv','.tsv')))
    return {'task_id': info['task_id'], 'decision_id': info['decision_id'], 'source_signature': info['source_signature'],
            'source_family': digest(primary_versions) if primary_versions else info['source_signature'],
            'question_sha256': info['question_sha256'], 'events_sha256': sha(path), 'records': records,
            'schemas': {row['name']: row['parameters'] for row in info['schemas']}}


def continuations(trace, contracts):
    records = trace['records']
    for index, anchor in enumerate(records):
        completion = contracts.get(anchor['name'], {}).get('observed_completion')
        if anchor['error'] or not completion or not anchor.get('value'):
            continue
        try:
            value = anchor['value']
            collection = value_at(value, completion['collection'])
            if (value_at(value, completion['success']) != completion['success_value'] or
                    value_at(value, completion['empty_findings']) != [] or not isinstance(collection, list) or not collection):
                continue
        except (KeyError, TypeError, IndexError):
            continue
        steps, witnesses = [], []
        for target in records[index + 1:index + 65]:
            if (target['error'] or contracts.get(target['name'], {}).get('read_only') is not True or
                    target.get('call_sequence', -1) <= anchor.get('result_sequence', float('inf'))):
                break
            bindings = {}
            for name, argument in target['arguments'].items():
                paths = [completion['collection'] + [n, field] for n, row in enumerate(collection)
                         if isinstance(row, dict) for field, candidate in row.items()
                         if isinstance(candidate, str) and candidate == argument]
                if len(paths) != 1:
                    break
                bindings[name] = paths[0]
            if not bindings or set(bindings) != set(target['arguments']):
                break
            images = [block for block in target['content'] if block.get('type') == 'image']
            if contracts[target['name']].get('image_output_required') and not images:
                break
            if images:
                references = {block.get('attachment', {}).get('attachmentId') for block in images}
                indices = {path[len(completion['collection'])] for path in bindings.values()}
                expected = {'sha256:' + collection[n].get('sha256', '') for n in indices}
                if not expected.issubset(references):
                    break
            if target['name'] not in trace['schemas'] or anchor['name'] not in trace['schemas']:
                break
            steps.append({'id': 'step_' + str(len(steps)), 'tool': target['name'],
                'schema_sha256': digest(trace['schemas'][target['name']]), 'bindings': bindings})
            witnesses.append(target['call_id'])
            ir = {'version': 1, 'kind': 'observed_anchor_read_continuation',
                'anchor': {'tool': anchor['name'], 'schema_sha256': digest(trace['schemas'][anchor['name']])},
                **completion, 'collection_length': len(collection), 'steps': list(steps)}
            covered = {path[len(completion['collection'])] for step in steps for path in step['bindings'].values()}
            if covered != set(range(len(collection))):
                continue
            yield ir, {'task_id': trace['task_id'], 'decision_id': trace['decision_id'],
                'source_signature': trace['source_signature'], 'question_sha256': trace['question_sha256'],
                'source_family':trace.get('source_family',trace['source_signature']),
                'events_sha256': trace['events_sha256'], 'anchor_call_id': anchor['call_id'], 'continuation_call_ids': list(witnesses)}


def mapped_continuations(trace, contracts):
    """Induce a per-item binding only from complete, uniform observed reads.

    All arguments must depend solely on the completed anchor. Parallel reads
    are therefore independent; a write, literal argument or missing image is
    still a boundary. Discovery below requires two distinct observed lengths,
    and certification a third source with an unseen length.
    """
    for ir, witness in continuations(trace, contracts):
        steps, count = ir['steps'], ir['collection_length']
        if len(steps) != count or not 1 <= count <= 64:
            continue
        pattern, indices = None, set()
        for step in steps:
            paths = list(step['bindings'].values())
            positions = {path[len(ir['collection'])] for path in paths}
            if len(positions) != 1:
                break
            position = next(iter(positions))
            if position in indices:
                break
            indices.add(position)
            current = {'id': 'item', 'tool': step['tool'], 'schema_sha256': step['schema_sha256'],
                       'bindings': {key: path[len(ir['collection'])+1:] for key, path in step['bindings'].items()}}
            if pattern is not None and current != pattern:
                break
            pattern = current
        else:
            if indices == set(range(count)):
                yield {key: value for key, value in ir.items() if key not in ('kind','steps','collection_length')} | {
                    'kind': 'observed_anchor_read_map', 'collection_min': 1, 'collection_max': 64, 'step': pattern
                }, {**witness, 'collection_length': count}


def discover_workflows(training, heldout, contracts, environment, *, opportunities=None):
    candidates = {}
    for trace in training:
        for ir, witness in continuations(trace, contracts):
            if len(ir['steps']) > 16:
                continue
            row = candidates.setdefault(digest(ir), {'ir': ir, 'witnesses': {}})
            row['witnesses'][trace.get('source_family',trace['source_signature'])] = witness
        for ir, witness in mapped_continuations(trace, contracts):
            row = candidates.setdefault(digest(ir), {'ir': ir, 'witnesses': {}})
            row['witnesses'][trace.get('source_family',trace['source_signature'])] = witness
    programs = []
    for key, candidate in sorted(candidates.items()):
        witnesses = list({row['decision_id']:row for row in candidate['witnesses'].values()}.values())
        if len(witnesses) < 2 or len({row['source_signature'] for row in witnesses}) < 2:
            continue
        mapped = candidate['ir']['kind'] == 'observed_anchor_read_map'
        lengths = {row['collection_length'] for row in witnesses} if mapped else set()
        if mapped and len(lengths) < 2:
            continue
        replay = []
        for trace in heldout:
            if trace.get('source_family',trace['source_signature']) in {row['source_family'] for row in witnesses}:
                continue
            if any(trace[field] == witness[field] for witness in witnesses
                   for field in ('decision_id', 'source_signature')):
                continue
            observations = mapped_continuations(trace, contracts) if mapped else continuations(trace, contracts)
            replay.extend(witness for ir, witness in observations if digest(ir) == key and
                          (not mapped or witness['collection_length'] not in lengths))
        programs.append({'id': 'ppt_flow_' + key[:24], 'ir': candidate['ir'], 'provenance': witnesses,
            'status': 'certified' if replay else 'candidate',
            'certification': {'status': 'passed' if replay else 'pending', 'scope': 'independent_observed_binding_replay',
                'independence_policy': 'ppt_distinct_source_decision_v2',
                'training_decisions': len(witnesses), 'independent_replay_decisions': len({row['decision_id'] for row in replay}),
                'replay': replay, 'new_model_requests': 0, 'quality_judgment_skipped': False}})
    from src.adapters.ppt.learning.ppt_write_learning import discover_write_programs
    programs.extend(discover_write_programs(training, heldout, contracts))
    if opportunities is not None:
        from src.adapters.ppt.learning.ppt_skill_opportunities import guide_candidates
        programs = guide_candidates(programs, opportunities)
    body = {'version': 1, 'kind': 'trace_learned_tool_continuations', 'environment_sha256': environment,
            'programs': programs[:16]}
    return {**body, 'digest': digest(body)}


def advance_workflow_learning(output, store, request, infos, turns, *, delivery, failure_infos=None):
    """Learn from immutable owned deliveries; evaluation tasks never become sources."""
    output, store = Path(output), Path(store)
    folder = store / 'workflows'
    folder.mkdir(exist_ok=True, mode=0o700)
    selected = read(folder / 'selected.json') if (folder / 'selected.json').exists() else {}
    if (folder / 'suspended.json').exists() or (store / 'suspended.json').exists() or selected.get('phase') == 'disabled':
        save(folder / 'status.json', {'status': 'withdrawn_requires_explicit_recertification', 'new_model_requests': 0})
        return
    from src.adapters.ppt.learning.ppt_skill_opportunities import skill_corpus, guide_candidates, failure_observations
    contracts = read(ROOT / 'scenarios/ppt_master/workflow-contracts.json')['tools']
    skill = ROOT / 'scenarios/ppt_master/SKILL.md'
    opportunities = skill_corpus(ROOT, contracts)
    opportunities['source_sha256'] = sha(skill)
    opportunity_path = folder / ('opportunities-' + digest(opportunities) + '.json')
    if not opportunity_path.exists():
        save(opportunity_path, opportunities)
    traces, locks, excluded_materials = [], {}, []
    failures = [failure for info in (failure_infos if failure_infos is not None else infos).values()
                for failure in failure_observations(info, contracts)]
    for turn in turns.values():
        lane = turn.get('learning_lane', 'baseline')
        info = infos.get(turn.get('lanes', {}).get(lane, {}).get('task_id'))
        if not info:
            continue
        try:
            trace = collect_workflow_trace(info)
            if not trace:
                continue
            material_locks = {}
            proof = delivery(output, turn, lane, material_locks, store=store, info=info)
        except (ValueError, KeyError, OSError, TypeError) as error:
            excluded_materials.append({'task_id': info.get('task_id'), 'reason': str(error)[:200]})
            continue
        if proof.get('mechanical_status') == 'passed':
            traces.append(trace)
            locks.update(material_locks)
            locks.update(info['locks'])
    save(folder / 'material-admission.json', {'accepted_task_ids': [trace['task_id'] for trace in traces],
         'excluded': excluded_materials, 'new_model_requests': 0})
    if failures:
        negative = {'version': 1, 'skill_sha256': opportunities['skill_sha256'], 'failures': failures,
                    'use': 'counterexamples_not_repair_programs', 'new_model_requests': 0}
        negative_path = folder / ('failures-' + digest(negative) + '.json')
        if not negative_path.exists():
            save(negative_path, negative)
    traces = sorted(traces,key=lambda row:row['task_id'])
    families=sorted({trace['source_family'] for trace in traces})
    environment = workflow_environment()
    # Discovery does not require a third demonstration. Keep tentative repeats
    # visible while independent certification still uses the existing policy.
    pending = discover_workflows(traces, [], contracts, environment, opportunities=opportunities)
    pending_path = folder / ('discovered-' + pending['digest'] + '.json')
    if not pending_path.exists():
        save(pending_path, pending)
    if len(families) < 3:
        save(folder / 'status.json', {'status': 'waiting_for_independent_certification',
            'eligible_source_families': len(families), 'discovered_candidates': len(pending['programs']),
            'certified_programs': 0, 'new_model_requests': 0})
        return
    # Historical leave-one-source-out certification. Only normal eligible
    # sources participate; current E/R tasks are rejected before collection.
    programs = {}
    for family in families:
        discovered = discover_workflows([trace for trace in traces if trace['source_family']!=family],
            [trace for trace in traces if trace['source_family']==family],contracts,environment,
            opportunities=opportunities)
        for program in discovered['programs']:
            if program['status'] == 'certified':
                if program['ir']['kind'] == 'observed_page_write_delivery':
                    # A third independent normal execution already witnesses
                    # these bindings. Admit it for use; quality and savings
                    # must be judged after an actual subsequent task.
                    program = {**program, 'certification': {**program['certification'],
                        'quality_deferred': True, 'runtime_followup_required': True,
                        'admission': 'independent_observed_write_trial'}}
                programs.setdefault(program['id'], program)
    # A third task need not naturally repeat the same recipe. Test candidates
    # discovered from two families on recorded content from the third instead.
    # This native equivalence check is not a scientific or cost evaluation.
    from src.adapters.ppt.learning.ppt_write_learning import discover_write_programs
    from src.adapters.ppt.learning.ppt_workflow_certification import certify_write_candidate, independent_training, execution_case
    attempts = set()
    native_attempts = 0
    candidate_inventory = {}
    for trace in reversed(traces):
        if native_attempts >= 2:
            break
        training = independent_training(traces, trace)
        for candidate in guide_candidates(discover_write_programs(training, [], contracts), opportunities):
            candidate_inventory.setdefault(candidate['id'], candidate)
            if candidate['id'] in programs or candidate['id'] in attempts or execution_case(candidate, trace) is None:
                continue
            # Failed native executions are remembered until their actual inputs
            # or implementation change; they must not starve other opportunities.
            snapshot = output / 'tasks' / trace['task_id'] / 'ppt-program-snapshot.json'
            component_environment = None
            if snapshot.is_file():
                from src.adapters.ppt.learning.ppt_workflow_certification import component_environment as component_signature
                pointer = read(snapshot)
                component_path = Path(pointer['library'])
                if not component_path.is_absolute():
                    component_path = store / component_path
                from src.adapters.ppt.learning.ppt_program_learning import checked
                component_path = checked(store, component_path, pointer['library_sha256'])
                component_environment = component_signature(component_path)
            attempt_key = digest({'program_id': candidate['id'], 'heldout': trace['events_sha256'],
                                  'environment': environment, 'component_environment': component_environment,
                                  'snapshot': sha(snapshot) if snapshot.is_file() else None})
            negative_attempt = folder / ('native-failed-' + attempt_key + '.json')
            if negative_attempt.exists():
                continue
            attempts.add(candidate['id'])
            native_attempts += 1
            certified = certify_write_candidate(output, store, request, candidate, trace)
            if certified:
                program, execution_locks = certified
                programs[program['id']] = program
                locks.update(execution_locks)
            else:
                save(negative_attempt, {'status': 'not_certified', 'program_id': candidate['id'],
                     'input_sha256': attempt_key, 'new_model_requests': 0, 'retry': 'only_after_input_or_environment_change'})
            if native_attempts >= 2:
                break
    inventory = {'skill_sha256': opportunities['skill_sha256'], 'environment_sha256': environment,
                 'candidates': list(candidate_inventory.values()), 'attempted': sorted(attempts),
                 'new_model_requests': 0, 'production_savings_proven': False}
    inventory_path = folder / ('candidates-' + digest(inventory) + '.json')
    if not inventory_path.exists():
        save(inventory_path, inventory)
    if not programs:
        save(folder / 'status.json', {'status': 'no_independently_replayed_continuation', 'new_model_requests': 0})
        return
    feedback = store / 'feedback-version.json'
    feedback_version = sha(feedback) if feedback.exists() else None
    retained, previous_locks = retained_workflows(output, folder, selected, request, environment, feedback_version)
    additions = [row for identity, row in programs.items() if identity not in retained]
    admitted = additions[:16 - len(retained)]
    if retained and not admitted:
        save(folder / 'status.json', {'status': 'certified_' + selected['phase'], 'library_digest': selected['library'][:-5],
            'retained_programs': len(retained), 'deferred_programs': len(additions), 'new_model_requests': 0,
            'learning_cost_in_execution': False})
        return
    if any(name in locks and locks[name] != version for name, version in previous_locks.items()):
        raise ValueError('ppt_workflow_evidence_changed_during_learning')
    body = {'version': 1, 'kind': 'trace_learned_tool_continuations', 'environment_sha256': environment,
            'programs': [*retained.values(), *admitted]}
    library = {**body, 'digest': digest(body)}
    path = folder / (library['digest'] + '.json')
    if path.exists() and read(path) != library:
        raise ValueError('workflow_library_changed')
    if not path.exists():
        save(path, library)
    save(folder / 'selected.json', {'user': request['user'], 'scope': request['scope'], 'phase': 'probation',
        'library': path.name, 'sha256': sha(path), 'environment_sha256': library['environment_sha256'],
        'feedback_version': feedback_version, 'evidence_locks': {**previous_locks, **locks}})
    save(folder / 'status.json', {'status': 'certified_probation', 'library_digest': library['digest'],
        'retained_programs': len(retained), 'added_programs': len(admitted), 'deferred_programs': len(additions) - len(admitted),
        'new_model_requests': 0, 'learning_cost_in_execution': False})
