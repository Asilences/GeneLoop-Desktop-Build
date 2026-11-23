"""Independent native execution checks for a trace-discovered write candidate.

The held-out task supplies recorded content, not a prescribed tool order. The
candidate still needs two source families; native replay is distinct from a
third historical occurrence and does not prove scientific quality or savings.
"""
from copy import deepcopy
from src.adapters.filesystem_paths import Path
import io
import posixpath
import hashlib
import re
from PIL import Image

from src.adapters.ppt.learning.ppt_program_learning import ROOT, read, save, sha, digest, certify_programs


def snapshot_native_assets(output, store, request, trace, case):
    """Freeze owned image parameters for this replay, not a historical visual verdict."""
    ids=set(case['setup_calls']+case.get('write_calls',[]))
    images=sorted({row['arguments']['content']['image'] for row in trace['records']
                   if row['call_id'] in ids and row['name']=='compose_ppt_page'
                   and isinstance(row['arguments'].get('content',{}).get('image'),str)})
    if not images:return []
    output,store=Path(output),Path(store)
    if not re.fullmatch('[a-f0-9]{32}',trace['task_id']):raise ValueError('workflow_asset_owner_changed')
    source=output/'tasks'/trace['task_id']
    state,effective=read(source/'task-state.json'),read(source/'effective-config.json')
    if (state.get('user_id')!=request['user'] or effective.get('user_id')!=request['user'] or state.get('status')!='completed' or
            state.get('scene')!='ppt' or effective.get('ppt_execution_strategy')!='ppt_master'):
        raise ValueError('workflow_asset_owner_changed')
    workspace=Path(effective['workspace'])
    if not workspace.is_absolute() or workspace.resolve()!=workspace.absolute():raise ValueError('workflow_asset_workspace_changed')
    if not store.is_relative_to(output) or store.resolve()!=store.absolute():raise ValueError('workflow_asset_store_changed')
    folder=store
    for name in ('workflows','asset-inputs'):
        folder=folder/name
        if folder.is_symlink() or (folder.exists() and (not folder.is_dir() or folder.resolve()!=folder.absolute())):
            raise ValueError('workflow_asset_store_changed')
        folder.mkdir(exist_ok=True,mode=0o700)
    assets=[]
    for logical in images:
        if not logical.startswith('/work/') or posixpath.normpath(logical)!=logical or '\\' in logical:
            raise ValueError('workflow_asset_path_invalid')
        rel=logical[6:]
        path=workspace/('outputs/code/'+rel[8:] if rel.startswith('outputs/') else rel if rel.startswith('inputs/') else 'code/'+rel)
        if (path.is_symlink() or path.resolve()!=path.absolute() or not path.is_file() or path.stat().st_nlink!=1 or
                not 0<path.stat().st_size<=30_000_000):raise ValueError('workflow_asset_path_changed')
        raw=path.read_bytes();version=hashlib.sha256(raw).hexdigest()
        if sha(path)!=version:raise ValueError('workflow_asset_source_changed')
        with Image.open(io.BytesIO(raw)) as image:
            if image.format not in ('PNG','JPEG'):raise ValueError('workflow_asset_image_required')
            ext='png' if image.format=='PNG' else 'jpg'
            image.verify()
        target=folder/(version+'.'+ext)
        if target.exists():
            if target.is_symlink() or target.stat().st_nlink!=1 or target.read_bytes()!=raw:raise ValueError('workflow_asset_snapshot_changed')
        else:
            with target.open('xb') as stream:stream.write(raw)
            target.chmod(0o600)
        assets.append({'original':logical,'ref':target.relative_to(output).as_posix(),'sha256':version,'bytes':len(raw),'extension':ext})
    return assets


def component_environment(library):
    """Native replay caches must include the page engine's broader code locks."""
    compatibility = ROOT / 'config/script-runtime-compatibility.json'
    policy = read(compatibility) if compatibility.is_file() else {}
    paths = {row['path']: row['current_path']
             for row in policy.get('artifact', {}).get('transitions', []) if row.get('current_path')}
    return digest({name: sha(ROOT / paths.get(name, name)) for name in read(library).get('code_locks', {})})



def independent_training(traces, heldout):
    """Split by provenance before selecting one witness per source family.

    A later revision often shares the same question across papers. Choosing it
    by task-id order must not hide distinct, already available initial tasks.
    """
    family = heldout.get('source_family', heldout['source_signature'])
    return [trace for trace in traces if trace.get('source_family', trace['source_signature']) != family
            and all(trace[key] != heldout[key] for key in ('decision_id', 'source_signature'))]

def execution_case(program, trace):
    ir = program['ir']
    writer, mode = ir['writer']['tool'], ir['mode']
    if writer not in ('create_ppt_page', 'compose_ppt_page') or mode not in ('new', 'revision'):
        return None
    policy = program.get('certification', {}).get('independence_policy')
    if policy not in (None, 'ppt_distinct_source_decision_v2'):
        return None
    independent_keys = ('decision_id', 'source_signature') if policy else ('decision_id', 'source_signature', 'question_sha256')
    if any(trace.get('source_family', trace['source_signature']) == row.get('source_family', row['source_signature'])
           or any(trace[key] == row[key] for key in independent_keys)
           for row in program['provenance']):
        return None
    successful = [row for row in trace['records'] if row['name'] == writer and not row['error']
                  and (writer != 'create_ppt_page' or isinstance(row['arguments'].get('parameters'), dict))
                  and (writer == 'compose_ppt_page' or
                       isinstance(row['arguments'].get('notes'), str) and row['arguments']['notes'].strip())]
    minimum = 2 if ir['writer'].get('repeated_page_run') else 1
    from src.adapters.ppt.learning.ppt_write_learning import page_runs
    from src.adapters.ppt.learning.ppt_program_learning import read
    contracts = read(ROOT / 'scenarios/ppt_master/workflow-contracts.json')['tools']
    runs = [witness['write_call_ids'] for observed, witness in page_runs(trace, contracts)
            if observed['writer']['tool'] == writer and observed['mode'] == mode
            and witness['observed_items'] >= minimum]
    # A single recorded revision can also be independently executed against its
    # earlier draft. It does not witness or certify an unobserved multi-page run.
    if mode == 'revision' and minimum == 1:
        runs.extend([[row['call_id']] for row in successful if row['arguments'].get('expected_page_sha256')])
    by_id = {row['call_id']: row for row in successful}
    for ids in reversed(runs):
        if not all(identity in by_id for identity in ids):
            continue
        writes = [by_id[identity] for identity in ids]
        target = writes[0]
        project = target['arguments']['project']
        setups = {}
        if mode == 'revision':
            for row in successful:
                args = row['arguments']
                if row['call_sequence'] < target['call_sequence'] and args['project'] == project:
                    setups[args['page']] = row['call_id']
        if mode == 'revision' and (any(row['arguments']['page'] not in setups for row in writes) or len(setups) < 2):
            continue
        witness = {key: trace[key] for key in ('task_id', 'decision_id', 'source_signature', 'question_sha256', 'events_sha256')}
        witness['source_family'] = trace.get('source_family', trace['source_signature'])
        return {'witness': witness, 'mode': mode, 'setup_calls': list(setups.values()),
                'write_calls': ids, 'revision_call': target['call_id'] if mode == 'revision' else None}
    return None


def certify_write_candidate(output, store, request, program, trace):
    case = execution_case(program, trace)
    selected = output / 'tasks' / trace['task_id'] / 'ppt-program-snapshot.json'
    needs_components = program['ir']['writer']['tool'] == 'create_ppt_page'
    if not case or needs_components and not selected.is_file():
        return None
    component = {}
    if needs_components:
        pointer = read(selected)
        if pointer.get('user') != request['user'] or pointer.get('scope') != request['scope'] or pointer.get('phase') not in ('active', 'probation'):
            return None
        library = Path(pointer['library'])
        if not library.is_absolute():
            library = store / library
        from src.adapters.ppt.learning.ppt_program_learning import checked
        library = checked(store, library, pointer['library_sha256'])
        component = {'component_library': library.relative_to(output).as_posix(), 'component_library_sha256': sha(library),
                     'component_environment_sha256': component_environment(library),
                     'component_snapshot': selected.relative_to(output).as_posix(), 'component_snapshot_sha256': sha(selected)}
    from src.adapters.ppt.learning.ppt_workflow_learning import workflow_environment
    assets=snapshot_native_assets(output,store,request,trace,case)
    plan = {'version': 1, 'kind': 'ppt_native_workflow_certification', 'user': request['user'], 'scope': request['scope'],
            'candidate': program, 'case': case, 'environment_sha256': workflow_environment(), 'assets':assets, **component}
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
            from src.adapters.ppt.learning.ppt_program_evaluation import publish_generation
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
    locks = {path.relative_to(output).as_posix(): sha(path), result_path.relative_to(output).as_posix(): sha(result_path)}
    locks.update({row['ref']:row['sha256'] for row in assets})
    if needs_components:
        locks[selected.relative_to(output).as_posix()] = sha(selected)
    return certified, locks
