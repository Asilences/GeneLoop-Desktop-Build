"""Independent native execution checks for a trace-discovered write candidate.

The held-out task supplies recorded content, not a prescribed tool order. The
candidate still needs two source families; native replay is distinct from a
third historical occurrence and does not prove scientific quality or savings.
"""
from copy import deepcopy
from pathlib import Path

from .ppt_program_learning import ROOT, read, save, sha, digest, certify_programs


def component_environment(library):
    """Native replay caches must include the page engine's broader code locks."""
    return digest({name: sha(ROOT / name) for name in read(library).get('code_locks', {})})



def independent_training(traces, heldout):
    """Split by provenance before selecting one witness per source family.

    A later revision often shares the same question across papers. Choosing it
    by task-id order must not hide distinct, already available initial tasks.
    """
    family = heldout.get('source_family', heldout['source_signature'])
    return [trace for trace in traces if trace.get('source_family', trace['source_signature']) != family
            and all(trace[key] != heldout[key] for key in ('decision_id', 'source_signature', 'question_sha256'))]

def execution_case(program, trace):
    ir = program['ir']
    if ir['writer']['tool'] != 'create_ppt_page' or ir['mode'] != 'revision':
        return None
    if any(trace.get('source_family', trace['source_signature']) == row.get('source_family', row['source_signature'])
           or any(trace[key] == row[key] for key in ('decision_id', 'source_signature', 'question_sha256'))
           for row in program['provenance']):
        return None
    successful = [row for row in trace['records'] if row['name'] == ir['writer']['tool'] and not row['error']
                  and isinstance(row['arguments'].get('parameters'), dict) and row['arguments'].get('notes')]
    for target in reversed(successful):
        if not target['arguments'].get('expected_page_sha256'):
            continue
        project = target['arguments']['project']
        setups = {}
        for row in successful:
            args = row['arguments']
            if row['call_sequence'] >= target['call_sequence']:
                break
            if args['project'] == project and not args.get('expected_page_sha256'):
                setups.setdefault(args['page'], row['call_id'])
        if target['arguments']['page'] not in setups or len(setups) < 2:
            continue
        witness = {key: trace[key] for key in ('task_id', 'decision_id', 'source_signature', 'question_sha256', 'events_sha256')}
        witness['source_family'] = trace.get('source_family', trace['source_signature'])
        return {'witness': witness, 'setup_calls': list(setups.values()), 'revision_call': target['call_id']}
    return None


def certify_write_candidate(output, store, request, program, trace):
    case = execution_case(program, trace)
    selected = output / 'tasks' / trace['task_id'] / 'ppt-program-snapshot.json'
    if not case or not selected.is_file():
        return None
    pointer = read(selected)
    if pointer.get('user') != request['user'] or pointer.get('scope') != request['scope'] or pointer.get('phase') not in ('active', 'probation'):
        return None
    library = Path(pointer['library'])
    if not library.is_absolute():
        library = store / library
    from .ppt_program_learning import checked
    library = checked(store, library, pointer['library_sha256'])
    from .ppt_workflow_learning import workflow_environment
    plan = {'version': 1, 'kind': 'ppt_native_workflow_certification', 'user': request['user'], 'scope': request['scope'],
            'candidate': program, 'case': case, 'environment_sha256': workflow_environment(),
            'component_library': library.relative_to(output).as_posix(), 'component_library_sha256': sha(library),
            'component_environment_sha256': component_environment(library),
            'component_snapshot': selected.relative_to(output).as_posix(), 'component_snapshot_sha256': sha(selected)}
    folder = store / 'workflows' / 'certification' / digest(plan)
    folder.mkdir(parents=True, exist_ok=True, mode=0o700)
    path = folder / 'plan.json'
    if path.exists() and read(path) != plan:
        raise ValueError('workflow_certification_plan_changed')
    if not path.exists():
        save(path, plan)
    result_path = folder / 'result.json'
    if not result_path.exists():
        if (folder / 'process.json').exists():
            return None  # Keep a failed/interrupted attempt; do not retry the same plan forever.
        result = certify_programs(path, folder, request.get('command_resources', {}), workflow=True)
        save(folder / 'process.json', {'exit_code': result.returncode, 'stderr': result.stderr[-4000:], 'model_requests': 0})
        if result.returncode or not result_path.exists():
            return None
    result = read(result_path)
    if (result.get('plan_sha256') != sha(path) or result.get('status') != 'passed' or
            result.get('environment_sha256') != plan['environment_sha256'] or not result.get('native_equivalence') or
            not result.get('unmodified_pages_preserved') or not result.get('preview_complete')):
        return None
    # Reuse current native certificates instead of asking the model to rebuild
    # a known page program merely because the surrounding runtime changed.
    # The ordinary publisher retains the original source/quality scope and
    # starts probation; it never converts this to a cost/quality promotion.
    recertified = folder / 'component-recertification' / 'library.json'
    if recertified.is_file():
        source_pointer = read(selected)
        page_library = read(recertified)
        ids = {row['id'] for row in page_library['programs']}
        groups = [row for row in source_pointer.get('groups', []) if ids.intersection(row['program_ids'])]
        if groups:
            support_turns = list(dict.fromkeys(ref for group in groups for ref in group['support_turns']))
            support = {key: list(dict.fromkeys(value for group in groups for value in group['support'][key]))
                       for key in groups[0]['support']}
            support_scopes = {ref: scope for group in groups for ref, scope in group.get('support_scopes', {}).items()}
            page_locks = {name: version for group in groups for name, version in group['evidence_locks'].items()}
            page_locks.update({selected.relative_to(output).as_posix(): sha(selected),
                               result_path.relative_to(output).as_posix(): sha(result_path),
                               recertified.relative_to(output).as_posix(): sha(recertified)})
            publication = store / ('program-' + digest({'library': page_library['digest'], 'native_result': sha(result_path)})[:24])
            publication.mkdir(exist_ok=True, mode=0o700)
            from .ppt_program_evaluation import publish_generation
            published = publish_generation(output, store, request, publication, page_library, page_locks, support_turns,
                                           support, 'native_source_page_recertification', support_scopes=support_scopes)
            if published:
                save(store / 'program-status.json', {'status': 'probation', 'origin': 'native_source_page_recertification',
                    'compilation_model_requests': 0, 'extra_provider_requests': 0, 'quality_cost_promoted': False})
    certified = deepcopy(program)
    certified['status'] = 'certified'
    certified['certification'] = {**program['certification'], 'scope': 'independent_native_write_execution',
        'status': 'passed', 'independent_replay_decisions': 1, 'replay': [case['witness']],
        'runtime_followup_required': True, 'native_execution': {'status': 'passed',
            'environment_sha256': plan['environment_sha256'], 'result': result_path.relative_to(output).as_posix(),
            'sha256': sha(result_path), 'plan_sha256': sha(path), 'model_requests': 0}}
    return certified, {path.relative_to(output).as_posix(): sha(path), result_path.relative_to(output).as_posix(): sha(result_path),
                       selected.relative_to(output).as_posix(): sha(selected)}
