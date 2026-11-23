"""Pass actual Artifact observations to the existing independent certification/Store.

No new learner, schema, execution backend or certificate authority is defined.
"""
import argparse
import ast
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import time


def prepare(runtime, extraction, output):
    sys.path.insert(0, str(Path(runtime).resolve()))
    from src.rsi.feedback.capability_feedback import file_ref, verify
    extraction, output = Path(extraction), Path(output)
    candidates = json.loads((extraction / 'artifact.json').read_text())
    if not candidates:
        raise ValueError('chartmimic_no_observed_artifact_candidates')
    output.mkdir(parents=True, exist_ok=False)
    summary = json.loads((extraction / 'summary.json').read_text())
    verify(summary['source'])
    source_trial = Path(summary['source']['path']).parent
    provenance = [file_ref(extraction / 'artifact.json'), file_ref(extraction / 'summary.json'),
                  summary['source'], file_ref(source_trial / 'effective.json')]
    (output / 'source-provenance.json').write_text(json.dumps(provenance, indent=2) + '\n')
    rows = []
    for candidate in candidates:
        witness = candidate['witness']
        # Every path/version below comes from the original native learner.
        first_input = next(iter(witness['input_paths'].values()))
        path = Path(first_input)
        workspace = next(parent for parent in path.parents if parent.name == 'workspace')
        execution_workspace = output / 'workspaces' / witness['task_id']
        if not execution_workspace.exists():
            shutil.copytree(workspace, execution_workspace)
            (execution_workspace / 'command-tmp').mkdir(exist_ok=True)
        rows.append({'task_id': witness['task_id'], 'scene': 'chartmimic-direct',
                     'workspace': str(execution_workspace), 'original_workspace': str(workspace),
                     'workspace_preparation': 'byte_copy_plus_empty_execution_temp_not_new_observation',
                     'candidates': [candidate]})
        if summary.get('source_use'):
            rows[-1]['source_use'] = summary['source_use']
    # One actual call can yield multiple candidates; keep one row per task.
    grouped = {}
    for row in rows:
        if row['task_id'] not in grouped:
            grouped[row['task_id']] = {**row, 'candidates': []}
        grouped[row['task_id']]['candidates'].extend(row['candidates'])
    (output / 'observations.json').write_text(json.dumps(list(grouped.values()), indent=2) + '\n')
    def shape(value):
        if isinstance(value, dict):
            return {key: shape(child) for key, child in value.items()}
        if isinstance(value, list):
            return [shape(value[0])] if value else []
        return 'boolean' if isinstance(value, bool) else 'number' if isinstance(value, (int, float)) else 'null' if value is None else 'string'
    def schema(contract_shape):
        # Project the existing native contract, not a stricter schema invented
        # from every deep field in the first example. Native opaque object slots
        # permit current API keyword mappings to vary within the admitted shape.
        if isinstance(contract_shape, str):
            return {'type': contract_shape}
        if 'object' in contract_shape:
            fields = contract_shape['object']
            return {'type': 'object', 'properties': {key: schema(child) for key, child in fields.items()},
                    'required': list(fields), 'additionalProperties': False}
        if 'array' in contract_shape:
            return {'type': 'array', 'items': schema(contract_shape['array'])}
        raise ValueError('chartmimic_unknown_native_input_shape')
    interfaces = []
    for candidate in candidates:
        inputs = [json.loads(Path(candidate['witness']['input_paths'][str(i)]).read_text())
                  for i in candidate['input_argument_indices']]
        interfaces.append({'program_id': candidate['id'], 'description': ast.get_docstring(ast.parse(candidate['source'])),
                           'input_shapes': [shape(value) for value in inputs],
                           'runtime_input_schemas': [schema(contract['shape']) for contract in candidate['inputs']],
                           'schema_scope': 'original_native_key_type_contract; input_shapes are observed examples, not extra fixed requirements'})
    (output / 'interface.json').write_text(json.dumps(interfaces, indent=2) + '\n')
    return {'observations': file_ref(output / 'observations.json'), 'interface': file_ref(output / 'interface.json')}


def certify(runtime, observations, validation_trial, output, materials_root, owner):
    validation_trial, output = Path(validation_trial), Path(output)
    effective = json.loads((validation_trial / 'effective.json').read_text())
    result = json.loads((validation_trial / 'result.json').read_text())
    if effective['role'] != 'certification' or result['status'] != 'completed':
        raise ValueError('chartmimic_independent_completed_binding_required')
    binding_files = effective.get('binding_files') or ['/work/plot-spec.json']
    if __package__:
        from .trial import binding_paths
    else:
        from trial import binding_paths
    binding_paths({'binding_files': [{'path': path} for path in binding_files]})
    # A completed binding turn may still have emitted malformed JSON. Diagnose
    # that actual input before a native matcher reports an ambiguous absence.
    for path in binding_files:
        current = validation_trial / 'workspace/code' / Path(path).name
        if not current.is_file():
            raise ValueError('chartmimic_current_bound_json_required')
        json.loads(current.read_text())
    sys.path.insert(0, str(Path(runtime).resolve()))
    from src.rsi.feedback.capability_feedback import file_ref
    from benchmarks.evolution.benchmark_script_materials import BenchmarkScriptMaterials
    from src.adapters.execution_learning_pipeline import advance_execution_learning
    output.mkdir(parents=True, exist_ok=False)
    worker = os.environ.get('SSS_PYTHON', 'python3')
    (output / 'worker.json').write_text(json.dumps({'launcher': worker,
        'version': subprocess.check_output([worker, '--version'], text=True).strip(),
        'render_packages': json.loads(subprocess.check_output([worker, '-I', '-c',
            'import json,importlib.metadata as m;print(json.dumps({n:m.version(n) for n in '
            '["matplotlib","numpy","scipy","Pillow"]}))'], text=True))}, indent=2)+'\n')
    validation_workspace = output / 'validation-workspace'
    shutil.copytree(validation_trial / 'workspace', validation_workspace)
    (validation_workspace / 'command-tmp').mkdir(exist_ok=True)
    # Parameter learning witnesses uploaded-input contracts. Pin the Agent's
    # actual current JSON just as the native file dispatcher does, unchanged.
    materialized = []
    for index, path in enumerate(binding_files):
        current = validation_workspace / 'code' / Path(path).name
        bound = validation_workspace / 'inputs' / ('current-chart-spec.json' if index == 0
            else 'current-binding-' + str(index) + '.json')
        with bound.open('xb') as stream:
            stream.write(current.read_bytes())
        bound.chmod(0o400)
        materialized.append({'virtual': path, 'source': file_ref(current), 'fixed_input': file_ref(bound),
            'scope': 'unchanged_current_Agent_JSON_like_native_dispatch'})
    held = {'task_id': effective['task_id'], 'scene': 'chartmimic-direct',
            'workspace': str(validation_workspace), 'original_workspace': str(validation_trial / 'workspace'),
            'workspace_preparation': 'byte_copy_plus_empty_execution_temp_not_new_observation',
            'binding_materialization': materialized[0],
            'additional_binding_materializations': materialized[1:], 'candidates': []}
    (output / 'validation.json').write_text(json.dumps(held, indent=2) + '\n')
    materials = BenchmarkScriptMaterials(owner, materials_root)
    provenance = Path(observations).parent / 'source-provenance.json'
    evidence = [file_ref(validation_trial / 'result.json'), file_ref(validation_trial / 'effective.json'),
                file_ref(output / 'worker.json')]
    if provenance.is_file():
        evidence.extend([file_ref(provenance), *json.loads(provenance.read_text())])
    outcome = advance_execution_learning(file_ref(observations), materials.materials, output / 'native',
        validation=file_ref(output / 'validation.json'), backend='artifact_motif',
        evidence=evidence)
    if outcome['status'] == 'registered':
        catalog = materials.catalog()
        (output / 'shared-catalog.json').write_text(json.dumps(catalog, indent=2) + '\n')
        outcome['shared_catalog'] = file_ref(output / 'shared-catalog.json')
    return outcome


def parameterize(args):
    """Use the original declaration learner, rather than rewrite the renderer."""
    # Check the real source role before loading any learner or opening a gate.
    source_trial = args.source_trial.resolve()
    effective = json.loads((source_trial / 'effective.json').read_text())
    result = json.loads((source_trial / 'result.json').read_text())
    source_use = None
    if (effective['role'] != 'learning' and getattr(args, 'next_generation', None)
            and getattr(args, 'retirement_evidence', None)):
        if __package__:
            from .source_use import retired_source
        else:
            from source_use import retired_source
        source_use = retired_source(source_trial, args.next_generation, args.retirement_evidence)
    if (effective['role'] != 'learning' and source_use is None) or result['status'] != 'completed':
        raise ValueError('chartmimic_completed_learning_source_required')
    runtime, output = args.runtime.resolve(), args.output.resolve()
    sys.path.insert(0, str(runtime))
    if args.model_profile == 'luna':
        os.environ['KOURI_MODELS_FILE'] = str(runtime / 'config/research-gpt-6-luna.json')
    from src.rsi.feedback.capability_feedback import file_ref, verify
    from benchmarks.evolution.benchmark_script_materials import BenchmarkScriptMaterials
    from src.adapters.script_parameter_learning import learn_pending_parameters
    raw = json.loads(verify(file_ref(args.observations)))
    candidates = [candidate for row in (raw if isinstance(raw, list) else [raw])
                  for candidate in row.get('candidates', [])
                  if not args.program_id or candidate['id'] == args.program_id]
    if len(candidates) != 1:
        raise ValueError('chartmimic_select_one_observed_program')
    candidate = candidates[0]
    if (candidate['witness']['task_id'] != effective['task_id']
            or candidate['witness'].get('source_task_mode') != 'normal_execution'):
        raise ValueError('chartmimic_actual_normal_learning_witness_required')
    output.mkdir(parents=True, exist_ok=False)
    evidence = [file_ref(source_trial / 'effective.json'), file_ref(source_trial / 'result.json'),
                *[file_ref(path) for path in args.learning_feedback]]
    configuration = {'format': 'chartmimic_parameter_learning_v1',
        'operation': 'original_declaration_parameter_learning', 'task_id': effective['task_id'],
        'role': 'parameter_learning',
        'execution_mode': 'replay_existing_model_reply' if args.proposal_response else 'paid' if args.call_model else 'preview',
        'source': file_ref(args.observations), 'source_program_id': candidate['id'],
        'adaptation_evidence': evidence, 'model_profile': args.model_profile,
        'learner': file_ref(runtime / 'src/adapters/script_parameter_learning.py'),
        'prompt': file_ref(runtime / 'config/script-parameter-learning.txt'),
        'budget_usd': None, 'request_limit': None, 'cumulative_ledger_reset': False,
        'quality_scope': 'source_equivalence_and_controlled_parameters; independent_task_quality_pending'}
    if args.model_profile == 'luna':
        from src.adapters.research_luna import MODEL, MAX_TOKENS
        configuration.update(model=MODEL, reasoning_effort='none', max_completion_tokens=MAX_TOKENS)
    else:
        from src.adapters.harness.capability.capability_proposal import MODEL, MAX_TOKENS
        configuration.update(model=MODEL, reasoning_effort='off', max_tokens=MAX_TOKENS)
    configuration['runtime_manifest'] = file_ref(runtime / 'source-manifest.json')
    if source_use:
        configuration['source_use'] = source_use
    configuration['scene_adapter'] = file_ref(Path(__file__))
    (output / 'effective.json').write_text(json.dumps(configuration, indent=2) + '\n')
    if not args.call_model and not args.proposal_response:
        return {'status': 'preview', **configuration}
    if args.render_python:
        os.environ['SSS_PYTHON'] = str(args.render_python.absolute())
    if args.proposal_response:
        from src.adapters.script_parameter_learning import parse_parameter_proposal, learn_parameters
        response_ref = file_ref(args.proposal_response)
        context_ref = file_ref(args.proposal_response.parent / 'prompt-context.json')
        context = json.loads(verify(context_ref))
        if not any(card['source_candidate_id'] == candidate['id'] and card['source'] == candidate['source']
                   for card in context['candidates']):
            raise ValueError('chartmimic_proposal_source_context_changed')
        response = json.loads(verify(response_ref))
        choice = response['choices'][0]
        if choice['finish_reason'] != 'stop':
            raise ValueError('chartmimic_complete_model_proposal_required')
        proposal = parse_parameter_proposal(choice['message']['content'])
        if proposal.pop('source_candidate_id', None) != candidate['id']:
            raise ValueError('chartmimic_proposal_candidate_changed')
        provenance = {'raw_response': response_ref, 'prompt_context': context_ref,
            'request_events': file_ref(args.proposal_response.parent / 'requests.jsonl'),
            'model_reported': response.get('model'),
            'declaration': proposal, 'scope': 'replay_actual_model_declaration; no_new_model_decision_or_task'}
        (output / 'model-declaration.json').write_text(json.dumps(provenance, indent=2) + '\n')
        started = time.monotonic()
        materials = BenchmarkScriptMaterials(args.owner, args.materials_root)
        outcome = learn_parameters(candidate, proposal, materials.materials, output / 'native',
            source_evidence=file_ref(args.observations), proposal_evidence=file_ref(output / 'model-declaration.json'))
        outcome = {**outcome, 'model_requests': 0, 'provider_requests': 0,
            'model_proposal_provenance': file_ref(output / 'model-declaration.json'),
            'elapsed_seconds': time.monotonic() - started, 'quality_scope': configuration['quality_scope']}
        (output / 'result.json').write_text(json.dumps(outcome, indent=2) + '\n')
        if outcome['status'] == 'registered':
            (output / 'shared-catalog.json').write_text(json.dumps(materials.catalog(), indent=2) + '\n')
        return outcome
    if args.env_file:
        for line in args.env_file.read_text().splitlines():
            if line.startswith('KOURI_API_KEY='):
                os.environ.setdefault('KOURI_API_KEY', line.split('=', 1)[1].strip().strip('"').strip("'"))
    if args.render_python:
        os.environ['SSS_PYTHON'] = str(args.render_python.absolute())
    from src.adapters.harness.capability.capability_proposal import CumulativeProposalGate
    options = {}
    if args.model_profile == 'luna':
        from src.adapters.research_luna import MODEL, MAX_TOKENS
        options = {'model': MODEL, 'max_tokens': MAX_TOKENS, 'reasoning_effort': 'none'}
    materials = BenchmarkScriptMaterials(args.owner, args.materials_root)
    started = time.monotonic()
    with CumulativeProposalGate(args.ledger_root, **options) as gate:
        outcome = learn_pending_parameters(candidate, materials.materials, gate, output / 'native',
            source_evidence=file_ref(args.observations), adaptation_evidence=evidence)
    # Gate attribution is per exact proposal directory, not its parent. Keep
    # every actual attempt instead of reporting an empty parent's zero cost.
    proposal_directories = sorted({path for path in gate.attribution.values()
        if Path(path).is_relative_to(output)})
    costs = [gate.costs(Path(path)) for path in proposal_directories]
    ids = sorted({rid for cost in costs for rid in cost['request_ids']})
    outcome = {**outcome, 'native_registration_model_requests': outcome.get('model_requests'),
        'model_requests': len(ids), 'provider_requests': len(ids), 'request_ids': ids,
        'observed_model_usd': sum(cost['observed_model_usd'] for cost in costs)
            if all(cost['observed_model_usd'] is not None for cost in costs) else None,
        'billing_usd': None, 'proposal_attempts_at_gate_close': costs,
        'elapsed_seconds': time.monotonic() - started, 'quality_scope': configuration['quality_scope']}
    (output / 'result.json').write_text(json.dumps(outcome, indent=2) + '\n')
    if outcome['status'] == 'registered':
        (output / 'shared-catalog.json').write_text(json.dumps(materials.catalog(), indent=2) + '\n')
    return outcome


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('operation', choices=['prepare', 'certify', 'parameterize'])
    parser.add_argument('--runtime', required=True, type=Path)
    parser.add_argument('--extraction', type=Path)
    parser.add_argument('--observations', type=Path)
    parser.add_argument('--validation-trial', type=Path)
    parser.add_argument('--materials-root', type=Path)
    parser.add_argument('--owner', default='chartmimic-interface-v2')
    parser.add_argument('--source-trial', type=Path)
    parser.add_argument('--program-id')
    parser.add_argument('--learning-feedback', type=Path, action='append', default=[])
    parser.add_argument('--ledger-root', type=Path)
    parser.add_argument('--env-file', type=Path)
    parser.add_argument('--model-profile', choices=['deepseek', 'luna'], default='deepseek')
    parser.add_argument('--render-python', type=Path)
    parser.add_argument('--call-model', action='store_true')
    parser.add_argument('--proposal-response', type=Path, help='Replay a real saved model reply with its matching source context; no new model request.')
    parser.add_argument('--next-generation')
    parser.add_argument('--retirement-evidence', type=Path)
    parser.add_argument('--output', required=True, type=Path)
    args = parser.parse_args()
    if args.proposal_response and args.call_model:
        parser.error('--proposal-response and --call-model are mutually exclusive')
    if args.operation == 'parameterize' and any(value is None for value in (
            args.source_trial, args.observations, args.materials_root, args.ledger_root)):
        parser.error('parameterize requires --source-trial, --observations, --materials-root and --ledger-root')
    if args.operation == 'certify' and args.render_python:
        os.environ['SSS_PYTHON'] = str(args.render_python.absolute())
    value = (parameterize(args) if args.operation == 'parameterize' else
             prepare(args.runtime, args.extraction, args.output) if args.operation == 'prepare' else
             certify(args.runtime, args.observations, args.validation_trial, args.output, args.materials_root, args.owner))
    print(json.dumps(value, indent=2))
