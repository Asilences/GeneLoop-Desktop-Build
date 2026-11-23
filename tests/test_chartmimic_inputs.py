"""Oracle isolation and immutable role boundaries for the scene adapter."""
import importlib.util
import io
import json
from pathlib import Path
import subprocess
import tarfile
import tempfile
import unittest
from types import SimpleNamespace
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location('chart_prepare', ROOT / 'scenarios/chartmimic/prepare.py')
prepare = importlib.util.module_from_spec(spec)
spec.loader.exec_module(prepare)


class ChartMimicInputsTest(unittest.TestCase):
    def test_compiled_group_keeps_dynamic_default_provenance_in_execution_view(self):
        from scenarios.chartmimic.trial import compiled_keyword_groups
        from scenarios.chartmimic.interface import execution_card
        default={'expression':"line_cfg['linestyle']",'input_slot':0,
                 'source_path':['configuration','line','linestyle'],'type':'string'}
        group={'callee':'ax.plot','input_slot':0,'pointer':'/series','field':'options','container_kind':'objects',
               'schema':{'properties':{'linestyle':{'type':'string'}},'additionalProperties':False},
               'default':{},'current_input_defaults':{'linestyle':default}}
        card={'id':'dynamic','input_schema':{'type':'object'},'input_contracts':[],
              'source_path':'/work/source.py','output_files':[],
              'parameter_interface':{'keyword_groups':[group]}}
        card['compiled_keyword_groups']=compiled_keyword_groups(card)
        view=execution_card(card)['compiled_keyword_groups'][0]
        self.assertEqual(view['current_input_defaults'],{'linestyle':default})
        self.assertEqual(view['default'],{})
        self.assertIn('original current-input defaults',view['default_semantics'])
        del group['current_input_defaults']
        self.assertEqual(compiled_keyword_groups(card)[0]['current_input_defaults'],{})

    def test_observed_coarse_budget_and_record_unions_preserve_native_contract(self):
        from scenarios.chartmimic.interface import opaque_type_hints, execution_card
        native={'object':{'rows':'array'}}
        self.assertEqual(opaque_type_hints(native,'object'),{})
        variants={'union':[{'object':{'x':'number'}},
                           {'object':{'x':{'array':'number'},'y':{'array':'number'}}}]}
        expanded={'object':{'rows':{'array':{'object':{'x':'number'}}}}}
        observed={'object':{'rows':{'array':variants}}}
        self.assertEqual(opaque_type_hints(expanded,observed),{'/rows/*':variants})
        card={'id':'coarse','input_schema':{'type':'object'},'input_contracts':[{'shape':expanded}],
            'observed_json_shapes':[observed],'source_path':'/work/source.py','output_files':['chart.png']}
        view=execution_card(card)
        self.assertEqual(view['input_contracts'],card['input_contracts'])
        self.assertEqual(view['observed_opaque_types']['0'],{'/rows/*':variants})
        self.assertIn('possible observed shapes',view['type_scope'])

    def test_menu_groups_only_value_and_file_views_of_the_same_program_version(self):
        from scenarios.chartmimic.trial import capability_menu
        common = {'interface': 'Original operation and limits.', 'input_contracts': [],
            'output_files': ['chart.png'], 'scope': 'requires_current_judgment',
            'source_sha256': 'same-source', 'program_id': 'same-program', 'library_sha256': 'library-a'}
        file = {**common, 'id': 'file-a', 'native_binding': 'artifact_files'}
        value = {**common, 'id': 'value-a', 'native_binding': 'artifact_json_values', 'file_interface_id': 'file-a'}
        other_version = {**file, 'id': 'file-b', 'library_sha256': 'library-b'}
        menu = capability_menu([file, value, other_version])
        self.assertEqual([entry['id'] for entry in menu], ['value-a', 'file-b'])
        self.assertEqual(menu[0]['file_interface_id'], 'file-a')
        self.assertEqual(menu[0]['source_description'], common['interface'])

    def test_execution_view_deduplicates_metadata_and_preserves_field_semantics(self):
        from scenarios.chartmimic.interface import execution_card
        contracts = [{'format': 'json', 'shape': {'object': {'grid': 'object', 'series': {'array': 'object'}}},
            'source_origin': 'uploaded_input'}]
        shapes = [{'object': {'grid': {'object': {'linewidth': 'number'}},
            'series': {'array': {'object': {'x': {'array': 'number'}, 'label': 'string'}}}}}]
        groups = [{'callee': 'ax.plot', 'keywords': {'linestyle': 'string'}, 'default': {}}]
        card = {'id': 'root', 'input_schema': {'type': 'object'}, 'input_contracts': contracts,
            'native_input_contracts': contracts, 'observed_json_shapes': shapes,
            'source_path': '/work/cached.py', 'output_files': ['chart.png', 'chart.pdf'],
            'input_roles': ['spec'], 'interface': 'Operation description already in the frozen menu.',
            'input_documentation': 'Source introduction.\nJSON interface\n--------------\n'
                "markers.face: 'same' -> series color; 'none' -> hollow.\n",
            'compiled_keyword_groups': groups,
            'parameter_interface': {'observed_json_shapes': shapes,
                'input_role_contracts': [{'format': 'json', 'shape': contracts[0]['shape']}],
                'defaults': {}, 'parameters_schema': {'type': 'object', 'properties': {}},
                'parameter_path': '/work/inputs/parameters.json', 'parameter_file_required': False,
                'native_input_order': [0]}}
        before = json.dumps(card, sort_keys=True)
        view = execution_card(card)
        self.assertEqual(view['input_contracts'], contracts)
        self.assertEqual(set(view['observed_opaque_types']['0']), {'/grid', '/series/*'})
        self.assertIn("'same' -> series color; 'none' -> hollow", view['field_documentation'])
        self.assertEqual(view['parameter_interface'], {'parameter_file_required': False, 'native_input_order': [0]})
        self.assertEqual(view['compiled_keyword_groups'], groups)
        self.assertEqual(json.dumps(card, sort_keys=True), before)

        value_card = {**card, 'native_binding': 'artifact_json_values', 'file_interface_id': 'file-root',
            'input_schema': {'type': 'object', 'properties': {'values': {'type': 'object',
                'properties': {'input0': {'type': 'object', 'properties': {'grid': {'type': 'object'}},
                    'required': ['grid'], 'additionalProperties': False}},
                'required': ['input0'], 'additionalProperties': False}}}}
        value_view = execution_card(value_card)
        self.assertEqual(value_view['input_schema']['properties']['values']['properties']['input0'], {'type': 'object'})
        self.assertEqual(value_view['input_contracts'], contracts)
        self.assertEqual(value_view['file_interface_id'], 'file-root')
        self.assertIn('grid', value_card['input_schema']['properties']['values']['properties']['input0']['properties'])

    def test_caller_schema_maps_file_and_value_interfaces_without_changing_native_contract(self):
        from scenarios.chartmimic.trial import caller_input_schema
        for field in ('inputs', 'values'):
            native = {'type': 'object', 'properties': {field: {'type': 'array' if field == 'inputs' else 'object'},
                'output': {'type': 'string'}}, 'required': [field, 'output'], 'additionalProperties': False}
            before = json.dumps(native, sort_keys=True)
            schema = caller_input_schema({'id': 'real-root', 'contract': {'input_schema': native}})
            current = 'input_files' if field == 'inputs' else 'values'
            self.assertEqual(set(schema['properties']), {'capability_id', current, 'output_directory'})
            self.assertEqual(schema['required'], ['capability_id', current, 'output_directory'])
            self.assertEqual(schema['properties'][current], native['properties'][field])
            self.assertEqual(json.dumps(native, sort_keys=True), before)

    def test_binding_files_follow_actual_json_roles_and_reject_outside_paths(self):
        from scenarios.chartmimic.trial import binding_paths, binding_specification
        self.assertEqual(binding_paths([{}]), ['/work/plot-spec.json'])
        files = [{'path': '/work/plot-spec.json', 'role': 'chart_spec'},
                 {'path': '/work/parameters.json', 'role': 'parameters'}]
        self.assertEqual(binding_paths([{'binding_files': files}]), [row['path'] for row in files])
        schemas = [{'type': 'object'}, {'type': 'object', 'required': ['alignment']}]
        specification = binding_specification([{'binding_files': files, 'runtime_input_schemas': schemas}])
        self.assertEqual(specification['parameters']['properties'], {'chart_spec': schemas[0], 'parameters': schemas[1]})
        self.assertEqual(specification['files'], files)
        with self.assertRaisesRegex(ValueError, 'current_json_binding_paths_required'):
            binding_paths({'binding_files': [*files, {'path': '/etc/private.json'}]})

    def test_malformed_binding_is_reported_before_loading_optional_runtime(self):
        from scenarios.chartmimic.learn import certify
        with tempfile.TemporaryDirectory() as temp:
            trial = Path(temp)
            (trial / 'workspace/code').mkdir(parents=True)
            (trial / 'effective.json').write_text(json.dumps({'role': 'certification'}))
            (trial / 'result.json').write_text(json.dumps({'status': 'completed'}))
            (trial / 'workspace/code/plot-spec.json').write_text('{"unfinished":1')
            with self.assertRaises(json.JSONDecodeError):
                certify(trial / 'missing-runtime', trial / 'unused', trial,
                        trial / 'new-output', trial / 'materials', 'diagnostic')
            self.assertFalse((trial / 'new-output').exists())

    def test_menu_preserves_complete_applicability_and_compiled_options_without_inline_schemas(self):
        from scenarios.chartmimic.trial import capability_menu
        applicability = 'Draw current series. Supports a single axes only; logarithmic axes are unsupported.'
        cards = [{'id': 'original-root', 'interface': applicability,
            'input_roles': ['chart_spec'], 'input_contracts': [{'format': 'json', 'shape': {'object': {}}}],
            'input_schema': {'type': 'object', 'properties': {'input_files': {'type': 'array'}}},
            'output_files': [{'path': 'chart.png', 'sha256': 'historical-version'}, {'path': 'chart.pdf'}],
            'scope': 'current_suitability_requires_judgment',
            'parameter_interface': {'keyword_groups': [{'callee': 'ax.plot', 'input_slot': 0,
                'pointer': '/series', 'field': 'options', 'container_kind': 'objects',
                'default': {},
                'schema': {'properties': {'linestyle': {'type': 'string'}}, 'additionalProperties': False}}]}}]
        before = json.dumps(cards, sort_keys=True)
        menu = capability_menu(cards)
        self.assertEqual(menu[0]['source_description'], applicability)
        group = menu[0]['compiled_keyword_groups'][0]
        self.assertEqual(group['keywords'], {'linestyle': 'string'})
        self.assertEqual(group['default'], {})
        self.assertFalse(group['additional_keywords'])
        self.assertEqual(menu[0]['outputs'], ['chart.png', 'chart.pdf'])
        self.assertNotIn('input_contracts', menu[0])
        self.assertNotIn('input_schema', menu[0])
        self.assertEqual(json.dumps(cards, sort_keys=True), before)

    def test_reference_code_never_enters_solver_tree(self):
        with tempfile.TemporaryDirectory() as temp:
            base = Path(temp)
            official = base / 'official'
            prompts = official / 'chart2code/prompts/DirectAgent'
            prompts.mkdir(parents=True)
            (prompts / 'gpt-4-vision-preview.json').write_text(json.dumps({'instruction': 'Draw {width} by {height}.'}))
            (official / 'dimentions_info.jsonl').write_text(json.dumps({
                'idx': 'line_1', 'width': 7, 'height': 4, 'code': 'SECRET_ORACLE_SOURCE'}))
            archive = base / 'data.tar.gz'
            with tarfile.open(archive, 'w:gz') as tar:
                for suffix, raw in [('.png', b'png-image-bytes'), ('.py', b'SECRET_ORACLE_SOURCE')]:
                    entry = tarfile.TarInfo('./direct_600/line_1' + suffix)
                    entry.size = len(raw)
                    tar.addfile(entry, io.BytesIO(raw))
            with patch.object(subprocess, 'check_output', return_value='official-sha\n'):
                manifest = prepare.prepare(official, archive, base / 'frozen', {'learning': ['line_1']})
            solver = base / 'frozen/solver'
            self.assertEqual(sorted(p.name for p in (solver / 'line_1').iterdir()), ['instruction.md', 'reference.png'])
            self.assertFalse(any(b'SECRET_ORACLE_SOURCE' in p.read_bytes() for p in solver.rglob('*') if p.is_file()))
            self.assertEqual((base / 'frozen/evaluation-only/line_1/line_1.py').read_bytes(), b'SECRET_ORACLE_SOURCE')
            self.assertEqual(manifest['tasks']['line_1']['role'], 'learning')

    def test_roles_cannot_overlap(self):
        with self.assertRaisesRegex(ValueError, 'disjoint_task_ids_required'):
            prepare.prepare('unused', 'unused', 'unused', {'learning': ['line_1'], 'successor': ['line_1']})

    def test_member_paths_cannot_escape(self):
        with self.assertRaisesRegex(ValueError, 'disjoint_task_ids_required'):
            prepare.prepare('unused', 'unused', 'unused', {'learning': ['../line_1']})

    def test_customized_target_image_cannot_be_mistaken_for_solver_input(self):
        with self.assertRaisesRegex(ValueError, 'customized_requires_original_image'):
            prepare.prepare('unused', 'unused', 'unused', {'learning': ['line_1']}, 'customized_600')

    def test_successor_is_refused_before_loading_optional_learner(self):
        extract_spec = importlib.util.spec_from_file_location('chart_extract', ROOT / 'scenarios/chartmimic/extract.py')
        extract_module = importlib.util.module_from_spec(extract_spec)
        extract_spec.loader.exec_module(extract_module)
        with tempfile.TemporaryDirectory() as temp:
            trial = Path(temp)
            (trial / 'effective.json').write_text(json.dumps({'role': 'successor'}))
            (trial / 'result.json').write_text(json.dumps({'status': 'completed'}))
            with self.assertRaisesRegex(ValueError, 'non_successor_task_required'):
                extract_module.extract(trial / 'no-runtime', trial, trial / 'output')
            self.assertFalse((trial / 'output').exists())

    def test_parameter_learning_refuses_successor_before_importing_or_paying(self):
        learn_spec = importlib.util.spec_from_file_location('chart_learn', ROOT / 'scenarios/chartmimic/learn.py')
        learn_module = importlib.util.module_from_spec(learn_spec)
        learn_spec.loader.exec_module(learn_module)
        with tempfile.TemporaryDirectory() as temp:
            trial = Path(temp)
            (trial / 'effective.json').write_text(json.dumps({'role': 'successor'}))
            (trial / 'result.json').write_text(json.dumps({'status': 'completed'}))
            args = SimpleNamespace(source_trial=trial, runtime=trial / 'missing-runtime', output=trial / 'out')
            with self.assertRaisesRegex(ValueError, 'completed_learning_source_required'):
                learn_module.parameterize(args)
            self.assertFalse(args.output.exists())


if __name__ == '__main__':
    unittest.main()
