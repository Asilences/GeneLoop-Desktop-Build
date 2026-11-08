"""Discover bounded data-flow continuations from owned normal tool traces.

Contracts describe tool effects and typed output fields. Tool order and argument
bindings come from adjacent successful calls, never from a supplied workflow.
"""
from pathlib import Path
import json
import sys

from .ppt_program_learning import digest, read, sha, save

ROOT = Path(__file__).resolve().parents[2]


def workflow_environment():
    files = read(ROOT / 'scenarios/ppt_master/workflow-contracts.json')['implementation_files']
    return digest({'platform': sys.platform, 'code_locks': {name: sha(ROOT / name) for name in files}})


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
    for sequence, line in enumerate(path.read_text(encoding='utf-8').splitlines()):
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
        previous = anchor
        for target in records[index + 1:index + 17]:
            if (target['error'] or contracts.get(target['name'], {}).get('read_only') is not True or
                    target.get('call_sequence', -1) <= previous.get('result_sequence', float('inf'))):
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
            previous = target
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


def discover_workflows(training, heldout, contracts, environment):
    candidates = {}
    for trace in training:
        for ir, witness in continuations(trace, contracts):
            row = candidates.setdefault(digest(ir), {'ir': ir, 'witnesses': {}})
            row['witnesses'][trace.get('source_family',trace['source_signature'])] = witness
    programs = []
    for key, candidate in sorted(candidates.items()):
        witnesses = list({row['decision_id']:row for row in candidate['witnesses'].values()}.values())
        if (len(witnesses) < 2 or len({row['source_signature'] for row in witnesses}) < 2 or
                len({row['question_sha256'] for row in witnesses}) < 2):
            continue
        replay = []
        for trace in heldout:
            if trace.get('source_family',trace['source_signature']) in {row['source_family'] for row in witnesses}:
                continue
            if any(trace[field] == witness[field] for witness in witnesses
                   for field in ('decision_id', 'source_signature', 'question_sha256')):
                continue
            replay.extend(witness for ir, witness in continuations(trace, contracts) if digest(ir) == key)
        programs.append({'id': 'ppt_flow_' + key[:24], 'ir': candidate['ir'], 'provenance': witnesses,
            'status': 'certified' if replay else 'candidate',
            'certification': {'status': 'passed' if replay else 'pending', 'scope': 'independent_observed_binding_replay',
                'training_decisions': len(witnesses), 'independent_replay_decisions': len({row['decision_id'] for row in replay}),
                'replay': replay, 'new_model_requests': 0, 'quality_judgment_skipped': False}})
    from .ppt_write_learning import discover_write_programs
    programs.extend(discover_write_programs(training, heldout, contracts))
    body = {'version': 1, 'kind': 'trace_learned_tool_continuations', 'environment_sha256': environment,
            'programs': programs[:16]}
    return {**body, 'digest': digest(body)}


def advance_workflow_learning(output, store, request, infos, turns, *, delivery):
    """Learn from immutable owned deliveries; evaluation tasks never become sources."""
    folder = store / 'workflows'
    folder.mkdir(exist_ok=True, mode=0o700)
    selected = read(folder / 'selected.json') if (folder / 'selected.json').exists() else {}
    if (folder / 'suspended.json').exists() or (store / 'suspended.json').exists() or selected.get('phase') == 'disabled':
        save(folder / 'status.json', {'status': 'withdrawn_requires_explicit_recertification', 'new_model_requests': 0})
        return
    traces, locks = [], {}
    for turn in turns.values():
        lane = turn.get('learning_lane', 'baseline')
        info = infos.get(turn.get('lanes', {}).get(lane, {}).get('task_id'))
        if not info:
            continue
        trace = collect_workflow_trace(info)
        if not trace:
            continue
        proof = delivery(output, turn, lane, locks, store=store, info=info)
        if proof.get('mechanical_status') == 'passed':
            traces.append(trace)
            locks.update(info['locks'])
    traces = sorted(traces,key=lambda row:row['task_id'])
    families=sorted({trace['source_family'] for trace in traces})
    if len(families) < 3:
        save(folder / 'status.json', {'status': 'waiting_for_three_independent_normal_decisions', 'new_model_requests': 0})
        return
    contracts = read(ROOT / 'scenarios/ppt_master/workflow-contracts.json')['tools']
    # Historical leave-one-source-out certification. Only normal eligible
    # sources participate; current E/R tasks are rejected before collection.
    programs = {}
    environment = workflow_environment()
    for family in families:
        discovered = discover_workflows([trace for trace in traces if trace['source_family']!=family],
            [trace for trace in traces if trace['source_family']==family],contracts,environment)
        for program in discovered['programs']:
            if program['status'] == 'certified' and program['ir']['kind'] != 'observed_page_write_delivery':
                programs.setdefault(program['id'], program)
    # A third task need not naturally repeat the same recipe. Test candidates
    # discovered from two families on recorded content from the third instead.
    # This native equivalence check is not a scientific or cost evaluation.
    from .ppt_write_learning import discover_write_programs
    from .ppt_workflow_certification import certify_write_candidate, independent_training, execution_case
    attempts = set()
    native_attempted = False
    for trace in reversed(traces):
        if native_attempted:
            break
        training = independent_training(traces, trace)
        for candidate in discover_write_programs(training, [], contracts):
            if candidate['id'] in programs or candidate['id'] in attempts or execution_case(candidate, trace) is None:
                continue
            attempts.add(candidate['id'])
            native_attempted = True
            certified = certify_write_candidate(output, store, request, candidate, trace)
            if certified:
                program, execution_locks = certified
                programs[program['id']] = program
                locks.update(execution_locks)
            break
    body = {'version': 1, 'kind': 'trace_learned_tool_continuations', 'environment_sha256': environment,
            'programs': list(programs.values())[:16]}
    library = {**body, 'digest': digest(body)}
    if not any(row['status'] == 'certified' for row in library['programs']):
        save(folder / 'status.json', {'status': 'no_independently_replayed_continuation', 'new_model_requests': 0})
        return
    path = folder / (library['digest'] + '.json')
    if path.exists() and read(path) != library:
        raise ValueError('workflow_library_changed')
    if not path.exists():
        save(path, library)
    save(folder / 'selected.json', {'user': request['user'], 'scope': request['scope'], 'phase': 'probation',
        'library': path.name, 'sha256': sha(path), 'environment_sha256': library['environment_sha256'],
        'feedback_version': sha(store / 'feedback-version.json') if (store / 'feedback-version.json').exists() else None, 'evidence_locks': locks})
    save(folder / 'status.json', {'status': 'certified_probation', 'library_digest': library['digest'],
        'new_model_requests': 0, 'learning_cost_in_execution': False})
