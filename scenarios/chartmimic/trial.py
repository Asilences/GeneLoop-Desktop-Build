"""ChartMimic scene IO around one original Harness session and cumulative gate.

This does not implement an Agent, miner, certifier, Store or Runtime. The
optional extraction uses the existing execution_learning_bridge unchanged.
"""
from __future__ import annotations

import argparse
import ast
import hashlib
import json
import os
import platform
from pathlib import Path
import re
import shutil
import subprocess
import sys
import threading
import time
from urllib.parse import urlsplit, urlunsplit
from uuid import uuid4

SCENE = Path(__file__).resolve().parent


def sha(raw):
    return hashlib.sha256(raw).hexdigest()


def save(path, value):
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')


def compiled_keyword_groups(card):
    return [{key: group[key] for key in ('callee', 'input_slot', 'pointer', 'field', 'container_kind')}
        | {'keywords': {key: rule['type'] for key, rule in group['schema']['properties'].items()},
           'default': group['default'], 'additional_keywords': group['schema']['additionalProperties'],
           'current_input_defaults': group.get('current_input_defaults', {}),
           'default_semantics': 'Missing local options or keys retain these original current-input defaults; '
                'other keys retain the static API defaults. JSON null is a value subject to the selected type.'}
        for group in card.get('parameter_interface', {}).get('keyword_groups', [])]


def program_view_key(card):
    return (card.get('program_id', card.get('source_sha256')), card.get('library_sha256'))


def capability_menu(cards):
    """Preserve source prose and project the actual compiled optional interface."""
    menu = []
    value_programs = {program_view_key(card) for card in cards
        if card.get('native_binding') == 'artifact_json_values'}
    for card in cards:
        if program_view_key(card) in value_programs and card.get('native_binding') != 'artifact_json_values':
            continue
        entry = {'id': card['id'], 'source_description': card['interface'],
            'input_roles': card.get('input_roles') or [
                {'slot': index, 'format': contract.get('format'), 'suffix': contract.get('suffix')}
                for index, contract in enumerate(card['input_contracts'])],
            'outputs': [item['path'] if isinstance(item, dict) else item
                for item in card.get('output_files', [])], 'scope': card['scope']}
        groups = compiled_keyword_groups(card)
        if groups:
            # These are compiled interface facts, independent of model prose.
            entry['compiled_keyword_groups'] = groups
        if card.get('native_binding') == 'artifact_json_values':
            entry['binding'] = 'values directly; Runtime exports current JSON and unchanged source'
            if card.get('file_interface_id'):
                entry['file_interface_id'] = card['file_interface_id']
        menu.append(entry)
    return menu


def caller_input_schema(capability):
    """Describe the scene tool arguments, preserving the native contract separately."""
    native = capability['contract']['input_schema']
    names = {'inputs': 'input_files', 'output': 'output_directory'}
    properties = {names.get(key, key): value for key, value in native['properties'].items()}
    properties['capability_id'] = {'type': 'string', 'const': capability['id']}
    return {**native, 'properties': properties,
        'required': ['capability_id', *[names.get(key, key) for key in native.get('required', [])]]}


def binding_paths(interface):
    metadata = interface[0] if isinstance(interface, list) and len(interface) == 1 else interface
    if not isinstance(metadata, dict):
        raise ValueError('chartmimic_one_program_binding_interface_required')
    files = metadata.get('binding_files', [{'path': '/work/plot-spec.json'}])
    paths = [item['path'] for item in files]
    if (not paths or paths[0] != '/work/plot-spec.json' or len(set(paths)) != len(paths)
            or any(not isinstance(path, str) or not re.fullmatch(r'/work/[A-Za-z0-9_-]+\.json', path)
                   for path in paths)):
        raise ValueError('chartmimic_current_json_binding_paths_required')
    return paths


def binding_specification(interface):
    metadata = interface[0] if isinstance(interface, list) else interface
    paths = binding_paths(interface)
    files = metadata.get('binding_files', [{} for _ in paths])
    schemas = metadata['runtime_input_schemas']
    if len(paths) != len(schemas):
        raise ValueError('chartmimic_actual_input_roles_and_schemas_required')
    roles = [item.get('role', 'input' + str(index)) for index, item in enumerate(files)]
    if len(set(roles)) != len(roles) or any(not re.fullmatch(r'[a-z][a-z0-9_]{0,63}', role) for role in roles):
        raise ValueError('chartmimic_actual_input_role_names_required')
    return {'format': 'chartmimic_current_json_binding_v1',
        'files': [{'role': role, 'path': path} for role, path in zip(roles, paths)],
        'parameters': {'type': 'object', 'properties': dict(zip(roles, schemas)),
            'required': roles, 'additionalProperties': False}}


def freeze_capability_context(args, runtime, directory, workspace):
    """Expose original Store cards/libraries and the native source cache unchanged."""
    from src.rsi.feedback.capability_feedback import file_ref, verify
    from src.capability.graph.capability_contract import validate_capability_snapshot, capability_ref
    supplied = None
    supplied_ref = None
    if args.capability_catalog:
        target = directory / 'material-catalog.frozen.json'
        shutil.copyfile(args.capability_catalog, target)
        supplied_ref = file_ref(target)
        supplied = json.loads(verify(supplied_ref))
        references = supplied['libraries']
    else:
        references = [file_ref(args.capability_library)] if args.capability_library else []
    libraries, native_caps, visible, snapshots = [], {}, [], []
    seen = set()
    cards = {row['capability']['id']: row for row in supplied['catalog']} if supplied else {}
    for index, reference in enumerate(references):
        if reference['sha256'] in seen:
            continue
        seen.add(reference['sha256'])
        raw = verify(reference)
        frozen = directory / ('capability-library-' + str(index) + '.frozen.json')
        frozen.write_bytes(raw)
        frozen.chmod(0o400)
        libraries.append(file_ref(frozen))
        catalog_script = (
            "import {buildArtifactCapabilities} from './src/adapters/artifact_capability_runtime.ts';"
            "import {buildArtifactValueCapabilities} from './src/adapters/script_capability_runtime.ts';"
            "const [path,owner,sha,values]=process.argv.slice(1);"
            "const file=buildArtifactCapabilities(path,owner,sha);"
            "const value=values==='yes'?buildArtifactValueCapabilities(path,owner,sha):{capabilities:[],catalog:[]};"
            "process.stdout.write(JSON.stringify({...file,capabilities:[...file.capabilities,...value.capabilities],"
            "catalog:[...file.catalog,...value.catalog]}));")
        native = json.loads(subprocess.check_output(['node', '--experimental-strip-types', '--input-type=module',
            '-e', catalog_script, str(frozen), args.capability_owner, reference['sha256'],
            'yes' if supplied else 'no'], cwd=runtime, text=True))
        snapshots.append(native['snapshot'])
        save(directory / ('native-catalog-' + str(index) + '.json'), native)
        source_cache = (
            "import {loadArtifactLibrary,provideArtifactPrograms,artifactProgramPath} from './src/adapters/artifact_motif_runtime.ts';"
            "const library=loadArtifactLibrary(process.argv[1]);provideArtifactPrograms({library,workspace:process.argv[2]});"
            "process.stdout.write(JSON.stringify(Object.fromEntries(library.programs.map(p=>[p.id,artifactProgramPath(library,p)]))));")
        paths = json.loads(subprocess.check_output(['node', '--input-type=module', '-e', source_cache,
            str(frozen), str(workspace)], cwd=runtime, text=True))
        programs = {program['id']: program for program in json.loads(raw)['programs']}
        native_cards = {row['capability']['id']: row for row in native['catalog']}
        for capability in native['capabilities']:
            if supplied and capability['id'] not in cards:
                continue
            native_caps[capability['id']] = capability
            program = programs[capability['implementation']['legacy_ref']['object_id']]
            learned = cards.get(capability['id'], {})
            card = {'id': capability['id'], 'interface': learned.get('description', program['interface']),
                'program_id': program['id'], 'library_sha256': reference['sha256'],
                'input_contracts': program['inputs'], 'input_schema': caller_input_schema(capability),
                'native_input_schema': capability['contract']['input_schema'],
                'native_binding': native_cards[capability['id']].get('native_binding', 'artifact_files'),
                'source_sha256': program['source_sha256'],
                'source_path': paths[program['id']],
                'output_files': program['certification']['cases'][0]['files'],
                'scope': 'certified_static_program; current_visual_suitability_requires_your_judgment'}
            card['input_documentation'] = ast.get_docstring(ast.parse(program['source'])) or ''
            for key in ('input_roles', 'parameter_interface', 'output_files',
                        'native_input_contracts', 'observed_json_shapes'):
                if key in learned:
                    card[key] = learned[key]
            card['compiled_keyword_groups'] = compiled_keyword_groups(card)
            card['interface_authority'] = 'native_input_contracts_and_compiled_keyword_groups; interface preserves source prose; compiled groups extend it; other applicability limits still apply'
            visible.append(card)
    if supplied:
        snapshot = validate_capability_snapshot(supplied['snapshot'], args.capability_owner)
        if {cap['id']: capability_ref(cap)['sha256'] for cap in snapshot['capabilities']} != {
                identifier: capability_ref(cap)['sha256'] for identifier, cap in native_caps.items()}:
            raise ValueError('chartmimic_material_catalog_native_libraries_changed')
    else:
        snapshot = snapshots[0] if snapshots else {'digest': None, 'roots': [], 'capabilities': []}
    bundle = directory / 'capability-bundle.frozen.json'
    file_views = {program_view_key(card): card['id'] for card in visible
        if card.get('native_binding') != 'artifact_json_values'}
    for card in visible:
        if card.get('native_binding') == 'artifact_json_values' and program_view_key(card) in file_views:
            card['file_interface_id'] = file_views[program_view_key(card)]
    menu = capability_menu(visible)
    if __package__:
        from .interface import execution_card
    else:
        from interface import execution_card
    save(bundle, {'snapshot': snapshot, 'libraries': libraries, 'capabilities': visible, 'menu': menu,
        'execution_capabilities': [execution_card(card) for card in visible]})
    return libraries, supplied_ref, file_ref(bundle), menu


def run(args):
    runtime = args.runtime.resolve()
    sys.path.insert(0, str(runtime))
    if args.model_profile == 'luna':
        os.environ['KOURI_MODELS_FILE'] = str(runtime / 'config/research-gpt-6-luna.json')
    from src.adapters.harness.capability.capability_proposal import CumulativeProposalGate, MODEL, MAX_TOKENS
    from src.adapters.harness.harness_runtime import create_harness
    from src.rsi.feedback.capability_feedback import file_ref
    from src.adapters.model_api import model_api_root
    provider, effort, wire_model = 'deepseek-official', 'off', 'deepseek-v4.1-flash'
    gate_options = {}
    if args.model_profile == 'luna':
        from src.adapters.research_luna import MODEL, MAX_TOKENS, PROVIDER, harness_patch
        provider, effort, wire_model = PROVIDER, 'none', MODEL
        gate_options = {'model': MODEL, 'max_tokens': MAX_TOKENS, 'reasoning_effort': effort}
    if args.env_file:
        # Use the same one-key private file convention as the existing native
        # scene pilot; do not add a dotenv dependency to the host SDK environment.
        for line in args.env_file.read_text().splitlines():
            if line.startswith('KOURI_API_KEY='):
                os.environ.setdefault('KOURI_API_KEY', line.split('=', 1)[1].strip().strip('"').strip("'"))
    manifest = json.loads((args.inputs / 'manifest.json').read_text())
    task = manifest['tasks'][args.task]
    solver = args.inputs / 'solver' / args.task
    for name, expected in [('reference.png', task['input_image_sha256']), ('instruction.md', task['instruction_sha256'])]:
        if sha((solver / name).read_bytes()) != expected:
            raise ValueError('chartmimic_frozen_input_changed')
    directory = args.output.resolve()
    directory.mkdir(parents=True, mode=0o700, exist_ok=False)
    source_snapshot = directory / 'source-snapshot'
    source_snapshot.mkdir()
    native_source = args.native_tools or (SCENE.parents[1] / 'src/adapters/research_native_tools.ts')
    shutil.copyfile(Path(__file__), source_snapshot / Path(__file__).name)
    shutil.copyfile(native_source, source_snapshot / 'native_tools.ts')
    workspace = directory / 'workspace'
    for name in ('inputs', 'code', 'outputs/code', 'command-tmp'):
        (workspace / name).mkdir(parents=True, exist_ok=True)
    shutil.copyfile(solver / 'reference.png', workspace / 'inputs/reference.png')
    recovery_refs = None
    if args.binding_interface and (args.capability_library or args.capability_catalog):
        raise ValueError('chartmimic_binding_stage_has_no_execution_catalog')
    capability_api = bool(args.capability_library or args.capability_catalog or args.expose_capability_api) and not args.binding_interface
    if args.resume_trial:
        previous = args.resume_trial.resolve()
        previous_effective = json.loads((previous / 'effective.json').read_text())
        source_use = None
        if (previous_effective['role'] != 'learning' and getattr(args, 'next_generation', None)
                and getattr(args, 'retirement_evidence', None)):
            if __package__:
                from .source_use import retired_source
            else:
                from source_use import retired_source
            source_use = retired_source(previous, args.next_generation, args.retirement_evidence)
        if (task['role'] != 'learning' or (previous_effective['role'] != 'learning' and source_use is None)
                or previous_effective['task_id'] != args.task
                or previous_effective['task']['input_image_sha256'] != task['input_image_sha256']):
            raise ValueError('chartmimic_recovery_requires_same_learning_task')
        recovery_refs = {'effective': file_ref(previous / 'effective.json'),
                         'result': file_ref(previous / 'result.json'), 'files': {}}
        if source_use:
            recovery_refs['source_use'] = source_use
            recovery_refs['scope'] = 'same_normal_task_continuation_for_new_generation_not_new_independent_sample'
        for name in ('plot.py', 'plot-spec.json'):
            source = previous / 'workspace/code' / name
            shutil.copyfile(source, workspace / 'code' / name)
            recovery_refs['files'][name] = file_ref(source)
    prompt = (solver / 'instruction.md').read_text() + (
        '\nThe reference image is /work/inputs/reference.png. Use read_image to inspect the actual image. '
        'Write and execute your complete reproducible Matplotlib source as /work/plot.py; '
        'save the resulting figure as /work/outputs/chart.png and /work/outputs/chart.pdf. '
        'Inspect your output and finish after delivering these files. The source and figures are required deliverables.')
    if args.program_layout.startswith('parameter-files-'):
        prompt = (solver / 'instruction.md').read_text() + (
            '\nThe reference image is /work/inputs/reference.png. Inspect its actual pixels with read_image. '
            + ('\n<new_program_branch>These generation instructions apply ONLY if you choose to author a new '
               'implementation after evaluating the available capability catalog.\n'
               if args.program_layout in ('parameter-files-v5', 'parameter-files-v6') and capability_api else '') +
            'Organize your own solution as a reusable program plus a separate current-instance JSON file. '
            'Infer the data, labels, layout and visual styling yourself from this image. Put instance-specific '
            'values in /work/plot-spec.json rather than inline in the Python algorithm. '
            'After imports, organize a clearly named current-context binding section at the beginning of '
            'the program or its entry function, before the reusable algorithm. Read the current arguments '
            'and JSON there and define the task-dependent data, text, colors, typography, layout and '
            'output paths together. The later plotting logic should reference these bound variables or '
            'explicit context fields; do not scatter task values through helper bodies. Moving a hardcoded '
            'instance value to a module constant alone does not make it a current input. '
            'Instance-owned text, colors and styles must also come from the current JSON, including keyword '
            'arguments and fallback defaults; avoid leaving a previous chart value hardcoded there. '
            'Design the JSON interface yourself and document all its fields in the program module docstring. Do not place a whole Python '
            'program or executable expressions inside the JSON. When writing new code, implement the algorithm yourself in /work/plot.py '
            'with two positional arguments: the current JSON file and a fresh output directory. '
            'Write files in one tool call, then invoke the program in its own execute call containing only '
            '`python3 /work/plot.py /work/plot-spec.json /work/outputs/<new-render-name>` '
            '(replace the placeholder with a new unused directory on every render; no mkdir, cd or extra commands). '
            'Have the program create that output directory and write chart.png and chart.pdf there. '
            'Produce reproducible artifacts, including deterministic PDF metadata without wall-clock timestamps; '
            'use a non-interactive plotting backend. This organization changes no visual requirements. '
            'Inspect the rendered output with read_image and deliver both the actual Python source and JSON '
            'together with the two figures. Do not stop after measuring the reference pixels.')
    if args.program_layout in ('parameter-files-v3', 'parameter-files-v4', 'parameter-files-v5', 'parameter-files-v6'):
        prompt += ('\nExecution order: create and run a complete first candidate BEFORE optional pixel-measurement '
            'or precision-refinement scripts. Then inspect that rendered candidate and revise as needed to meet '
            'the same original visual requirements. Keep current values in JSON and keep implementation code '
            'separate throughout revision. Do not spend the task only analyzing the reference without a deliverable.')
    if args.program_layout == 'parameter-files-v6':
        prompt += ('\nNew implementation configuration boundary: collect current per-instance API keyword configuration into '
            'clearly named mapping slots in the JSON/context section at the beginning. Prefer forwarding '
            'those bound mappings to the fixed, ordinary library calls instead of baking the current '
            'choice of keyword values or implicit visual defaults into helper code. '
            'Group the named configuration mappings within one top-level context/configuration object; '
            'choose its keys and interface yourself, with datasets kept separately when useful. '
            'Keep the executable control flow and API choices in Python. Configuration mappings contain only data: never '
            'Python code, expressions, executable instructions, or dynamic method names. Design the '
            'actual interface yourself from this task and document which mappings go to which static '
            'public APIs and which fields are required versus optional. Do not build a general JSON '
            'execution engine. A complete first draft and the original visual fidelity remain required.')
    if args.program_layout in ('parameter-files-v5', 'parameter-files-v6') and capability_api:
        prompt += '\n</new_program_branch>\n'
    if args.resume_trial:
        prompt += ('\nThis continues the SAME learning task from its own earlier real draft, not a new sample. '
            'Its actual model-authored /work/plot.py and /work/plot-spec.json are already present. Inspect '
            'them and the reference image, revise the draft in response to the native feedback below, '
            'then execute it in the standalone call and inspect the actual delivered figures. '
            'Preserve the documented JSON interface wherever it already expresses the intended property; '
            'use its appropriate current field instead of hardcoded instance-specific implementation values. '
            'Do not encode a Python implementation in JSON, synthesize traces, or claim certification.\n')
        if args.learning_feedback:
            shutil.copyfile(args.learning_feedback, source_snapshot / 'learning-feedback.json')
            recovery_refs['learning_feedback'] = file_ref(source_snapshot / 'learning-feedback.json')
            prompt += 'Actual native feedback (not chart answers):\n' + args.learning_feedback.read_text()
    current_binding_paths = []
    binding_ref = None
    if args.binding_interface:
        if task['role'] != 'certification':
            raise ValueError('chartmimic_binding_interface_requires_certification_role')
        current_binding_paths = binding_paths(json.loads(args.binding_interface.read_text()))
        binding = binding_specification(json.loads(args.binding_interface.read_text()))
        binding['source_interface'] = file_ref(args.binding_interface)
        save(source_snapshot / 'binding-specification.json', binding)
        binding_ref = file_ref(source_snapshot / 'binding-specification.json')
        shutil.copyfile(SCENE / 'binding_tools.ts', source_snapshot / 'binding_tools.ts')
        prompt = (
            'Your current stage is independent JSON input binding, not program generation. '
            'First inspect the actual reference with read_image; your next action must call submit_binding '
            'with the COMPLETE current JSON value for every declared input role. The tool writes these fixed files: '
            + ', '.join(current_binding_paths) + '. '
            'Use the actual input roles and required fields in the observed schema below. Infer current '
            'values visually for this initial binding. Do not run pixel/crop/font-measurement scripts before '
            'writing it. Do not leave any required field as a placeholder. '
            'This is an independent input-binding stage for an observed drawing program. Inspect the actual '
            'reference pixels at /work/inputs/reference.png. Infer the CURRENT image data and all its visual '
            'parameters yourself. Submit all roles together using the following observed interface. '
            'The field types are interface information, not current chart values. The tool validates the original '
            'input schemas and serializes exactly your values; correct any returned validation errors yourself. '
            'Do not use shell/Python serialization scripts, empty fallback objects, a new drawing implementation '
            'or the program awaiting certification; the original independent certifier will execute it separately. '
            'Do not claim rendered output or quality. Do not invent undocumented interface fields; explain '
            'any unsupported requirements separately in the final response. Finish only after all required '
            'JSON bindings are written and syntax-valid. '
            'The downstream chart task retains its original full visual requirements:\n' +
            (solver / 'instruction.md').read_text() + '\nObserved program interface and required input schema:\n' +
            args.binding_interface.read_text())
    capability_ref, material_ref, bundle_ref = None, None, None
    capability_libraries, visible_catalog = [], []
    if capability_api:
        shutil.copyfile(SCENE / 'capability_tools.ts', source_snapshot / 'capability_tools.ts')
        shutil.copyfile(SCENE / 'interface.py', source_snapshot / 'interface.py')
    if capability_api:
        capability_libraries, material_ref, bundle_ref, visible_catalog = freeze_capability_context(
            args, runtime, directory, workspace)
        capability_ref = capability_libraries[0] if capability_libraries else None
    if capability_api:
        if args.program_layout in ('parameter-files-v5', 'parameter-files-v6'):
            prompt += ('\nExecution routing: inspect the current image and the actual catalog below, then choose '
                'reuse or new implementation based on the current required chart properties. Prefer an existing '
                'program when its documented interface covers those properties. For a reuse choice, create '
                'the CURRENT JSON with that interface and execute capability_call; the standalone python3 '
                'command and source-authoring instructions in <new_program_branch> do not apply to this branch. '
                'The native Runtime exports the unchanged historical source with the figures. Do not write a '
                'surrogate renderer that reimplements a program you chose to reuse. If the catalog is empty '
                'or a required property is unsupported, explain the gap. You may compose cached routines with '
                'new control flow or drawing calls, or use <new_program_branch> for a new implementation. '
                'Ordinary source composition is distinct from certified native execution. '
                'Both branches retain the original visual requirements and require inspecting actual output.\n')
        prompt += ('\nThe learned capability menu below is frozen for this task (it may be empty). '
            'Independently certified capabilities, when listed, are an optional alternative to '
            'writing the drawing implementation. The menu preserves each operation and applicability boundary. '
            'source_description is retained source prose and may predate a learned extension. '
            'compiled_keyword_groups defines the actual supported API, current object, option keys/types and '
            'local defaults and current_input_defaults. Missing local options keep the original CURRENT '
            'input defaults, never the first example value. These compiled additions take precedence over an outdated source-description '
            'claim that the same option is fixed. Other applicability limits still apply. '
            'Use capability_list with a selected capability_id to read its execution interface, field '
            'documentation and cached source path before binding inputs; calling it without an ID returns '
            'only this menu. The selected view omits descriptions already in the menu and duplicate '
            'audit metadata. include_audit=true retrieves the complete original card when needed. '
            'If suitable, infer the CURRENT inputs yourself and follow the selected input_schema: '
            'input_files binds your JSON files; values binds JSON objects directly as input0, input1, etc. '
            'The audit native_input_schema describes internal Runtime binding, not capability_call arguments. '
            'For EVERY capability_call, including refinements after changing current inputs, choose a NEW '
            'unused output directory under /work/outputs (for example /work/outputs/render-1, then render-2). '
            'Existing output directories are immutable; deleting files or recreating the same directory does not make it new. '
            'The original Runtime exports its unchanged program with the '
            'figures and direct JSON inputs, satisfying the reproducible source deliverable. Inspect the artifacts. '
            'Cached source_path files are available for inspection and '
            'ordinary composition; use capability_call for certified native execution. Input shapes shown '
            'in observed_opaque_types are observed examples, not extra required fields; input_contracts '
            'remain the native admission contract. Field documentation preserves source-authored option semantics. '
            'If unsuitable, use ordinary tools and explain the fallback.\n' +
            json.dumps({'frozen_capability_menu': visible_catalog}, ensure_ascii=False))
    prompt += ('\nShell commands use the mounted /work paths. The reference already exists at '
        '/work/inputs/reference.png; attachment cache locations returned by the image service are host-managed. '
        '/work/inputs contains read-only original materials. Create CURRENT JSON files in writable /work '
        '(for example /work/plot-spec.json) or /work/outputs. Input role names do not specify directories. '
        'For a file capability call, pass these current paths as input_files; the adapter pins its own '
        'read-only Runtime input copies. '
        'Use a new unused output directory for every render or refinement and deliver the actual final '
        'source, current JSON and figure paths; do not assume the final directory has a fixed name. '
        'Use installed python3 or shell redirection to write files; the container has no apply_patch command.')
    (directory / 'prompt.txt').write_text(prompt)
    effective = {'format': 'chartmimic_trial_v1', 'task_id': args.task, 'role': task['role'],
        'model': MODEL, 'wire_model': wire_model, 'provider': 'Kouri AI', 'sdk_provider': provider,
        'reasoning_effort': effort, 'sdk_reasoning_effort': 'off', 'mode': 'baseline', 'budget_usd': None, 'request_limit': None,
        'max_tokens': MAX_TOKENS, 'cumulative_ledger_reset': False, 'timeout_seconds': args.timeout,
        'official_commit': manifest['official_commit'], 'inputs_manifest': file_ref(args.inputs / 'manifest.json'),
        'runtime': str(runtime), 'image': args.image, 'tool_order': ['execute', 'read_image'], 'mcp_servers': 0,
        'native_tools': file_ref(source_snapshot / 'native_tools.ts'),
        'trial_adapter': file_ref(source_snapshot / Path(__file__).name),
        'image_transport': 'original_bytes_into_Harness_attachment_service; SDK_may_preprocess', 'task': task,
        'quality': 'pending_official_evaluation', 'learning_enabled': False}
    effective['program_layout'] = args.program_layout
    effective['same_learning_task_recovery'] = recovery_refs
    effective['evaluation_use'] = 'frozen_role'
    if args.development_retest_of:
        original = json.loads(args.development_retest_of.read_text())
        if (original['task_id'] != args.task
                or original['task']['input_image_sha256'] != task['input_image_sha256']):
            raise ValueError('chartmimic_development_retest_task_mismatch')
        effective['evaluation_use'] = 'development_retest_not_new_unseen_evidence'
        effective['development_retest_of'] = file_ref(args.development_retest_of)
    endpoint = urlsplit(model_api_root())
    effective['upstream_endpoint'] = urlunsplit((endpoint.scheme,
        (endpoint.hostname or '') + (':'+str(endpoint.port) if endpoint.port else ''), endpoint.path, '', ''))
    effective['model_profile'] = args.model_profile
    if args.model_profile == 'luna':
        effective.update(wire_output_limit_field='max_completion_tokens',
            pricing_scope='official_OpenAI_reference_rates_not_Kouri_invoice',
            model_config=file_ref(runtime / 'config/research-gpt-6-luna.json'),
            provider_adapter=file_ref(runtime / 'src/adapters/research_luna.py'))
    if args.render_python:
        # Keep the venv launcher path: resolving it selects the base environment
        # and silently changes the worker's installed rendering dependencies.
        worker_python = args.render_python.absolute()
        effective['artifact_worker'] = {'launcher': str(worker_python),
            'binary': file_ref(worker_python),
            'version': subprocess.check_output([str(worker_python), '--version'], text=True).strip(),
            'render_packages': json.loads(subprocess.check_output([str(worker_python), '-I', '-c',
                'import json,importlib.metadata as m; print(json.dumps({n:m.version(n) for n in '
                '["matplotlib","numpy","scipy","Pillow"]}))'], text=True))}
    effective['binding_interface'] = file_ref(args.binding_interface) if args.binding_interface else None
    effective['binding_files'] = current_binding_paths if args.binding_interface else None
    effective['binding_specification'] = binding_ref
    effective['binding_tools'] = file_ref(source_snapshot / 'binding_tools.ts') if args.binding_interface else None
    effective['capability_library'] = capability_ref
    effective['capability_libraries'] = capability_libraries
    effective['material_catalog'] = material_ref
    effective['capability_bundle'] = bundle_ref
    effective['capability_tools'] = file_ref(source_snapshot / 'capability_tools.ts') if capability_api else None
    effective['interface_projection'] = file_ref(source_snapshot / 'interface.py') if capability_api else None
    effective['capability_owner'] = args.capability_owner if capability_api else None
    if capability_api:
        effective.update(mode='successor_reuse' if capability_ref else 'baseline', learning_enabled=False,
            tool_order=['execute', 'read_image', 'capability_list', 'capability_call'],
            matching='model_owned_optional_capability_selection_current_binding')
    if args.binding_interface:
        effective['mode'] = 'certification_input_binding'
        effective['tool_order'].append('submit_binding')
    effective.update(python=sys.version, operating_system=platform.platform(),
        node_version=subprocess.check_output(['node', '--version'], text=True).strip(),
        package_lock=file_ref(runtime / 'package-lock.json'),
        runtime_source_manifest=file_ref(runtime / 'source-manifest.json')
            if (runtime / 'source-manifest.json').is_file() else None,
        compression='no_application_compaction_configured; native_events_retained',
        matching='baseline_no_library_no_matcher', embedding_model=None,
        provider_retry='pinned_Harness_provider_default; raw_requests_retained')
    save(directory / 'effective.json', effective)
    if not args.call_model:
        return {'status': 'preview', 'effective': effective, 'directory': str(directory)}
    container = 'geneloop-chart-' + uuid4().hex[:12]
    result = {'status': 'failed', 'model_requests': None, 'quality': 'pending_official_evaluation'}
    started = time.monotonic()
    def command(argv, **kw):
        return subprocess.run(argv, capture_output=True, text=True, check=True, **kw)
    gate = None
    try:
        command(['docker', 'run', '-d', '--name', container, '--network', 'none', '--cpus', '2', '--memory', '4g',
            '-v', str(workspace / 'code') + ':/work',
            '-v', str(workspace / 'inputs') + ':/work/inputs:ro',
            '-v', str(workspace / 'outputs/code') + ':/work/outputs', args.image, 'sleep', 'infinity'])
        result['container_image_id'] = command(['docker', 'inspect', '--format', '{{.Image}}', container]).stdout.strip()
        patch = directory / 'native.patch.yml'
        rows = [{'id': 'system-prompt', 'config': {
            'personaPrefix': 'Complete the supplied chart task using the available native tools. All commands run only in its isolated container.',
            'personaSuffix': 'Use the supplied image as evidence and deliver the requested files.'}},
            {'insert': [{'id': 'chartmimic-native-tools', 'name': (source_snapshot / 'native_tools.ts').as_uri()}]}]
        if args.program_layout == 'parameter-files-v4':
            rows[0]['config']['personaPrefix'] = (
                'You author concrete executable artifacts, not analysis-only reports. After viewing the supplied '
                'reference image, write a COMPLETE FIRST JSON binding and, when requested, its runnable program '
                'before any pixel-measurement or crop-diagnostic scripts. Read the image visually for this first '
                'artifact. Pixel diagnostics may refine an existing rendered draft later; they must not prevent '
                'initial delivery. Keep all original visual fidelity requirements for the final result. '
                'In an input-binding-only stage, write the current JSON and finish; do not start diagnostic '
                'measurement loops. All ordinary commands are confined to the task container.')
        if args.program_layout in ('parameter-files-v5', 'parameter-files-v6'):
            rows[0]['config']['personaPrefix'] = (
                'Complete the chart using a suitable existing capability or a new program. Inspect the current '
                'image and the catalog, then decide applicability. When choosing an existing capability, bind '
                'current parameters and execute its exposed native capability_call; its exported historical '
                'source satisfies the code deliverable. Source-authoring and standalone python3 instructions '
                'apply only when you choose the new-program branch for an empty or unsuitable catalog. '
                'Keep current values in JSON and bind them at the entry of any new code. Produce a complete '
                'first binding and rendered draft before optional pixel diagnostics; refine the actual output '
                'as needed to meet the same original visual quality. Commands run in the isolated container.')
        if capability_api:
            rows[-1]['insert'].append({'id': 'chartmimic-certified-capabilities',
                'name': (source_snapshot / 'capability_tools.ts').as_uri()})
        if args.binding_interface:
            rows[-1]['insert'].append({'id': 'chartmimic-current-json-binding',
                'name': (source_snapshot / 'binding_tools.ts').as_uri()})
            rows[0]['config']['personaPrefix'] = (
                'Independently infer the current chart inputs from the supplied image. Use read_image, '
                'then submit_binding for all actual JSON roles. The host validates and serializes your values; '
                'correct tool-reported errors. Do not write serialization scripts or a renderer, run the '
                'program awaiting certification, or replace the chart with placeholders. Rendering and '
                'independent certification happen after this input stage.')
        with CumulativeProposalGate(args.ledger_root, **gate_options) as gate:
            gate.current = directory
            env = {**gate.environment(), 'GENELOOP_CHART_CONTAINER': container,
                'GENELOOP_CHART_WORKSPACE': str(workspace), 'GENELOOP_CHART_RUN': str(directory),
                'DSH_HOME': str(directory / 'dsh'), 'SSS_SCENARIO_TOOLS': '["execute","read_image"]'}
            if capability_api:
                env.update(GENELOOP_CHART_RUNTIME=str(runtime), GENELOOP_CHART_LIBRARY=capability_ref['path'] if capability_ref else '',
                    GENELOOP_CHART_LIBRARY_SHA256=capability_ref['sha256'] if capability_ref else '', GENELOOP_CHART_OWNER=args.capability_owner,
                    GENELOOP_CHART_TASK=args.task+'-'+directory.name,
                    GENELOOP_CHART_BUNDLE=bundle_ref['path'], GENELOOP_CHART_BUNDLE_SHA256=bundle_ref['sha256'],
                    SSS_SCENARIO_TOOLS='["execute","read_image","capability_list","capability_call"]')
            if args.render_python:
                env['SSS_PYTHON'] = str(args.render_python.absolute())
            if args.binding_interface:
                env.update(GENELOOP_CHART_RUNTIME=str(runtime), GENELOOP_CHART_BINDING=binding_ref['path'],
                    GENELOOP_CHART_BINDING_SHA256=binding_ref['sha256'],
                    SSS_SCENARIO_TOOLS=json.dumps(effective['tool_order']))
            if args.model_profile == 'luna':
                rows.extend([harness_patch(env['DEEPSEEK_BASE_URL']), {'id': 'llm-retry', 'disabled': False}])
            patch.write_text('\n'.join('- ' + json.dumps(row) for row in rows) + '\n')
            def observe(notification):
                if notification.method == 'session.event':
                    with (directory / 'events.jsonl').open('a') as stream:
                        stream.write(json.dumps(notification.payload.get('event'), ensure_ascii=False) + '\n')
            try:
                with create_harness(root=runtime, patches=(str(runtime / 'config/semantic-sdk.patch.yml'), str(patch)),
                    env=env, provider=provider, model=MODEL, max_tokens=MAX_TOKENS,
                    cwd=str(directory), runtime_cwd=str(directory), request_timeout_seconds=args.timeout) as client:
                    # Cancel the original session; never launch a second model loop.
                    session = 'chartmimic-' + uuid4().hex
                    def cancel():
                        from pydantic import BaseModel
                        class Cancelled(BaseModel):
                            accepted: bool
                        evidence = {'requested_at': time.time()}
                        try:
                            reply = client.client.request('session/cancel', {'sessionId': session}, response_model=Cancelled, timeout_seconds=10)
                            evidence['accepted'] = reply.accepted
                        except Exception as error:
                            evidence['error_type'] = type(error).__name__
                        finally:
                            save(directory / 'cancel.json', evidence)
                            if evidence.get('accepted') is not True:
                                client.close()
                    timer = threading.Timer(args.timeout, cancel)
                    timer.daemon = True
                    timer.start()
                    try:
                        reply = client.run(prompt, session_id=session, on_notification=observe)
                        (directory / 'answer.txt').write_text(reply.final_response or '')
                        result.update(status='completed' if reply.finish_reason == 'completed' else 'incomplete', finish_reason=reply.finish_reason)
                    finally:
                        timer.cancel()
                        timer.join()
            finally:
                pass
        result.update(gate.costs(directory))
        result['artifacts'] = {p.relative_to(workspace).as_posix(): file_ref(p)
            for p in workspace.rglob('*') if p.is_file() and not p.is_symlink()}
        calls = [json.loads(line) for line in (directory / 'native-tools.jsonl').read_text().splitlines()]
        result['image_reads'] = [row for row in calls if row['name'] == 'read_image']
        figure_prefix = 'outputs/code/rendered' if args.program_layout.startswith('parameter-files-') else 'outputs/code'
        result['output_present'] = all((workspace / name).is_file() for name in ('code/plot.py', figure_prefix+'/chart.png', figure_prefix+'/chart.pdf'))
        if args.binding_interface:
            result['binding_present'] = all((workspace / 'code' / Path(path).name).is_file()
                for path in current_binding_paths)
        if capability_ref:
            result['ordinary_output_present'] = result['output_present']
            result['reuse_output_present'] = (all((workspace / (figure_prefix+'/'+name)).is_file()
                for name in ('chart.png','chart.pdf','geneloop_reused_program.py'))
                and (workspace / 'code/plot-spec.json').is_file())
            result['output_present'] = result['ordinary_output_present'] or result['reuse_output_present']
        if args.program_layout.startswith('parameter-files-') and not args.binding_interface:
            if __package__:
                from .delivery import audit
            else:
                from delivery import audit
            # The existing auditor selects the actual final answer/image/native
            # receipt and checks source/input/artifact hashes, including refinements.
            delivery = audit(directory)
            save(directory / 'final-delivery.json', delivery)
            result['delivery_audit'] = file_ref(directory / 'final-delivery.json')
            result['delivery_status'] = delivery['status']
            result['output_present'] = bool(delivery.get('source') and delivery.get('inputs') and delivery.get('figures'))
            if capability_ref:
                result['ordinary_output_present'] = delivery['status'] == 'ordinary_source_and_parameters_present'
                result['reuse_output_present'] = delivery.get('native_unchanged_delivery', False)
    except Exception as error:
        result['error'] = type(error).__name__ + ':' + str(error)
    finally:
        subprocess.run(['docker', 'rm', '-f', container], capture_output=True)
        if gate is not None and hasattr(gate, 'state'):
            result.update(gate.costs(directory))
        result['elapsed_seconds'] = time.monotonic() - started
        save(directory / 'result.json', result)
    return result


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--runtime', required=True, type=Path)
    parser.add_argument('--model-profile', choices=['deepseek', 'luna'], default='deepseek',
                        help='Isolated research provider; does not change production defaults.')
    parser.add_argument('--inputs', required=True, type=Path)
    parser.add_argument('--task', required=True)
    parser.add_argument('--image', default='geneloop-chartmimic:20261109')
    parser.add_argument('--ledger-root', required=True, type=Path)
    parser.add_argument('--env-file', type=Path)
    parser.add_argument('--output', required=True, type=Path)
    parser.add_argument('--timeout', type=float, default=600)
    parser.add_argument('--program-layout', choices=['normal', 'parameter-files-v2', 'parameter-files-v3', 'parameter-files-v4', 'parameter-files-v5', 'parameter-files-v6'], default='normal')
    parser.add_argument('--binding-interface', type=Path)
    parser.add_argument('--resume-trial', type=Path, help='Recover this same learning task from its own actual code/JSON.')
    parser.add_argument('--next-generation')
    parser.add_argument('--retirement-evidence', type=Path)
    parser.add_argument('--learning-feedback', type=Path, help='Existing native failure evidence for a learning recovery.')
    parser.add_argument('--development-retest-of', type=Path,
                        help='Original frozen pair plan; label this reused task as development, not new unseen evidence.')
    parser.add_argument('--native-tools', type=Path, help='Trusted self-contained native IO module to snapshot.')
    parser.add_argument('--capability-library', type=Path)
    parser.add_argument('--capability-catalog', type=Path, help='Original CapabilityMaterials catalog with accumulated native libraries and learned interfaces.')
    parser.add_argument('--expose-capability-api', action='store_true',
                        help='Expose the same tool schemas with an empty learned catalog for the paired baseline.')
    parser.add_argument('--capability-owner', default='chartmimic-interface-v2')
    parser.add_argument('--render-python', type=Path, help='Original Artifact worker interpreter with pinned rendering dependencies.')
    parser.add_argument('--call-model', action='store_true')
    args = parser.parse_args()
    if args.capability_library and args.capability_catalog:
        parser.error('choose --capability-library or --capability-catalog')
    if args.timeout <= 0:
        parser.error('--timeout must be positive')
    if args.learning_feedback and not args.resume_trial:
        parser.error('--learning-feedback requires --resume-trial')
    result = run(args)
    print(json.dumps(result, ensure_ascii=False, indent=2))
