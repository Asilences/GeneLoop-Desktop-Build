"""Adapt model-proposed Python helpers to the original Script material path.

Input wrappers are deterministic host preparation. Native Script probes and
certificates retain their original model_construction evidence scope. Task
quality and autonomous recursive learning require separate real observations.
"""
from __future__ import annotations

import copy
import json
from pathlib import Path
import subprocess
from itertools import islice

from jsonschema import Draft202012Validator

from .capability_contract import (
    capability_digest, create_capability_snapshot, validate_capability_snapshot,
)
from .capability_feedback import file_ref, verify
from .capability_improvement import save
from .capability_materials import CapabilityMaterials
from .capability_scene import ROOT
from .capability_script_execution import execute as native_execute
from .capability_script_learning import learn as native_learn
from .file_lock import exclusive_lock


def _catalog(library, owner):
    verify(library)
    result = subprocess.run(['node', 'scripts/run-script-capability.mjs', '--catalog',
                             '--library', library['path'], '--owner', owner],
                            cwd=ROOT, capture_output=True, text=True, encoding='utf-8', timeout=90)
    if result.returncode:
        raise ValueError('benchmark_script_native_catalog_failed:' + result.stdout + result.stderr)
    return json.loads(result.stdout)


def _canonical_json(value):
    """Use the native JSON.stringify wire representation, including number keys."""
    capability_digest(value)
    result = subprocess.run(['node', '-e',
        'let s="";process.stdin.setEncoding("utf8");process.stdin.on("data",x=>s+=x);'
        'process.stdin.on("end",()=>process.stdout.write(JSON.stringify(JSON.parse(s))));'],
        input=json.dumps(value, ensure_ascii=False, allow_nan=False),
        capture_output=True, text=True, encoding='utf-8', timeout=30)
    if result.returncode:
        raise ValueError('benchmark_script_json_encoding_failed')
    return result.stdout.encode('utf-8')


def _payload(reference):
    raw = verify(reference)
    text = raw.decode('utf-8')
    try:
        value = json.loads(text.removeprefix('\ufeff'))
    except json.JSONDecodeError:
        return {'text': text}, 'utf8_text'
    return {'data': value}, 'json_value'


def _validate_execution_arguments(capability, arguments, encoding):
    errors = list(islice(Draft202012Validator(
        capability['contract']['input_schema']).iter_errors(arguments), 3))
    if not errors:
        return
    details = [{'path': list(error.absolute_path), 'validator': error.validator,
                'expected': json.dumps(error.validator_value, ensure_ascii=False)[:240],
                'actual_type': type(error.instance).__name__,
                'message': error.message[:320]} for error in errors]
    raise ValueError('benchmark_capability_input_schema_invalid_before_dispatch:' + json.dumps({
        'encoding': encoding, 'errors': details,
        'hint': 'Tool value is the run(value) input. input_file wraps JSON as {data:...} '
                'and other UTF-8 files as {text:...}. Use the listed input schema and '
                'the original text file when the function requires text.'}, ensure_ascii=False))


def _witnesses_source(text, source):
    if source in text or json.dumps(source, ensure_ascii=False) in text:
        return True
    try:
        value = json.loads(text)
    except json.JSONDecodeError:
        return False
    pending = [value]
    while pending:
        current = pending.pop()
        if isinstance(current, dict):
            pending.extend(current.values())
        elif isinstance(current, list):
            pending.extend(current)
        elif isinstance(current, str) and current == source:
            return True
    return False


def _native_failure_feedback(directory, error):
    """Project existing trusted native records; referenced files stay unchanged."""
    native = Path(directory) / 'native'
    names = ('executed-source.py', 'entrypoint.json', 'observations.json', 'certification.json',
             'library.json', 'certifier-stdout.log', 'certifier-stderr.log',
             'source/admission-error.json', 'heldout/admission-error.json',
             'source/source-stdout.txt', 'source/source-stderr.txt',
             'heldout/source-stdout.txt', 'heldout/source-stderr.txt')
    paths = [Path(directory) / 'request.json', Path(directory) / 'preparation.json',
             *[native / name for name in names]]
    paths.extend(sorted(native.glob('compile-[0-9]*/admission-error.json')))
    references = []
    diagnostics = []
    parse_errors = []
    for path in paths:
        if not path.is_file() or path.is_symlink():
            continue
        reference = file_ref(path)
        references.append(reference)
        if path.name not in ('admission-error.json', 'certification.json'):
            continue
        try:
            value = json.loads(verify(reference))
            if not isinstance(value, dict):
                raise ValueError('native_diagnostic_object_required')
            rows = value.get('rejected', []) if path.name == 'certification.json' else [value]
            for row in rows:
                if not isinstance(row, dict):
                    continue
                detail = row.get('diagnostic', row)
                if not isinstance(detail, dict):
                    detail = row
                diagnostics.append(({'error': row.get('reason', detail.get('error')), **detail}, reference))
        except (ValueError, UnicodeDecodeError) as failure:
            parse_errors.append({'evidence_id': 'evidence_' + reference['sha256'],
                                 'error': type(failure).__name__ + ':' + str(failure)})
    located = getattr(error, 'script_diagnostics', None)
    if isinstance(located, dict) and not any(value == located for value, _ in diagnostics):
        diagnostics.append((located, None))
    cards = []
    for value, reference in diagnostics[:4]:
        card = {key: value[key] for key in ('kind', 'error', 'source_space', 'line', 'column') if key in value}
        source_line = value.get('source_line')
        if isinstance(value.get('literal'), str):
            card['literal'] = value['literal'][:160]
        if isinstance(source_line, str):
            card.update(source_line=source_line[:240], source_line_characters=len(source_line))
        if reference is not None:
            card['evidence_id'] = 'evidence_' + reference['sha256']
        cards.append(card)
    return ({'message': 'Native Script construction was rejected. Inspect the recorded native diagnostics '
                       'and source coordinates before revising the candidate. Independent admission and '
                       'input-dependence requirements remain authoritative.',
             'stage': 'native_script_construction', 'native_error': str(error)[:300],
             'native_diagnostics': cards, 'native_diagnostic_count': len(diagnostics),
             'native_records': [{'name': str(Path(ref['path']).relative_to(directory)),
                                 'evidence_id': 'evidence_' + ref['sha256']} for ref in references],
             'diagnostic_read_errors': parse_errors,
             'read_tool': 'evolution_read(kind=evidence,id=evidence_id,section=content); JSON records support json_path'},
            references)


class BenchmarkScriptMaterials:
    """A thin owner-scoped adapter around CapabilityMaterials and native Script."""

    def __init__(self, owner, directory, *, learn=None, catalog=None, execute=None,
                 publication_store=None):
        if not isinstance(owner, str) or not owner.strip():
            raise ValueError('benchmark_script_owner_required')
        self.owner = owner
        self.directory = Path(directory).resolve()
        self.directory.mkdir(parents=True, exist_ok=True, mode=0o700)
        self.materials = CapabilityMaterials(self.directory / 'materials', owner)
        self.publication_store = Path(publication_store).resolve() if publication_store is not None else (
            self.directory / 'publication-store')
        self._learn = learn or native_learn
        self._catalog = catalog or _catalog
        self._execute = execute or native_execute

    def catalog(self):
        """Rebuild the original native catalogs from registered library bytes."""
        capabilities = {}
        roots = {}
        cards = {}
        libraries = []
        for material in self.materials.records():
            if material['backend'] != 'script_motif':
                continue
            native = self._catalog(material['library'], self.owner)
            snapshot = validate_capability_snapshot(native['snapshot'], self.owner)
            libraries.append(material['library'])
            for cap in snapshot['capabilities']:
                capabilities[cap['id']] = cap
            for ref in snapshot['roots']:
                roots[ref['id']] = ref
            for card in native.get('catalog', []):
                cards[card['capability']['id']] = card
        snapshot = create_capability_snapshot(self.owner, list(roots.values()), list(capabilities.values()))
        publication_head = None
        if self.publication_store.exists():
            from .benchmark_capability_publication import original_store_catalog
            published = original_store_catalog(snapshot, self.publication_store)
            snapshot = published['snapshot']
            publication_head = published['head']
            by_id = {cap['id']: cap for cap in snapshot['capabilities']}
            for row in published['catalog']:
                reference = row['capability']
                if reference['id'] not in cards:
                    cap = by_id[reference['id']]
                    descriptions = [(cards.get(step['capability']['id'], {}).get('description')
                                     or 'a certified operation') for step in cap['implementation'].get('steps', [])]
                    cards[reference['id']] = {'capability': reference,
                        'description': 'Learned composition of ' + ' followed by '.join(descriptions),
                        'input_schema': cap['contract']['input_schema'],
                        'output_schema': cap['contract']['output_schema'],
                        'certification_scope': 'heldout_native_source_equivalence',
                        'publication_sha256': row['publication_sha256']}
        return {'owner': self.owner, 'snapshot': snapshot, 'catalog': list(cards.values()),
                'libraries': libraries, 'publication_head': publication_head}

    def acquire(self, program, examples, source_evidence, opportunity, *, large_output=False):
        """Certify a real model helper on two explicit, distinct input files."""
        if (not isinstance(program, dict) or program.get('mode') != 'json'
                or program.get('interface') != 'function_v1'
                or not isinstance(program.get('source'), str) or not program['source'].strip()
                or not isinstance(program.get('description'), str) or not program['description'].strip()):
            raise ValueError('benchmark_script_program_interface_invalid')
        if not isinstance(examples, (list, tuple)) or len(examples) < 2:
            raise ValueError('benchmark_script_two_examples_required')
        if not isinstance(opportunity, str) or not opportunity.strip():
            raise ValueError('benchmark_script_opportunity_required')
        source_text = verify(source_evidence).decode('utf-8')
        if not _witnesses_source(source_text, program['source']):
            raise ValueError('benchmark_script_model_source_not_witnessed')
        for reference in examples:
            verify(reference)
        if examples[0]['sha256'] == examples[1]['sha256']:
            raise ValueError('benchmark_script_distinct_input_bytes_required')
        key = capability_digest({'program': program, 'examples': list(examples),
                                 'source_evidence': source_evidence, 'opportunity': opportunity,
                                 'large_output': large_output})
        directory = self.directory / 'acquisitions' / key
        directory.mkdir(parents=True, exist_ok=True, mode=0o700)
        with exclusive_lock(directory / '.lock'):
            result_path = directory / 'result.json'
            if result_path.exists():
                previous = json.loads(result_path.read_text(encoding='utf-8'))
                if previous['status'] != 'registered':
                    prior_error = ValueError(previous.get('error', 'previous_native_acquisition_failed'))
                    if isinstance(previous.get('script_diagnostics'), dict):
                        prior_error.script_diagnostics = previous['script_diagnostics']
                    diagnostic, references = _native_failure_feedback(directory, prior_error)
                    result_ref = file_ref(result_path)
                    diagnostic['result_evidence_id'] = 'evidence_' + result_ref['sha256']
                    resumed = {**previous, 'diagnostic': diagnostic, 'evidence_refs': [*references, result_ref]}
                    resumed.pop('script_diagnostics', None)
                    return resumed
                combined = self.catalog()
                return {**previous, 'catalog': combined, 'snapshot': combined['snapshot']}
            save(directory / 'request.json', {'program': program, 'examples': list(examples),
                 'source_evidence': source_evidence, 'opportunity': opportunity,
                 'certification_examples': list(examples[:2]),
                 'origin': 'model_construction', 'preparation': 'host_file_to_value_wrapper',
                 'independence_scope': 'distinct_source_bytes; host retains original task identities'})
            outcome = {'status': 'failed', 'origin': 'model_construction',
                       'scope': 'source_equivalence_not_semantic_quality',
                       'model_requests': 0, 'measured_net_benefit': None,
                       'request': file_ref(directory / 'request.json')}
            failure = None
            try:
                cases = []
                preparations = []
                for index, reference in enumerate(examples[:2]):
                    value, encoding = _payload(reference)
                    payload = directory / ('input-' + str(index) + '.json')
                    payload.write_bytes(_canonical_json(value))
                    prepared = file_ref(payload)
                    cases.append({'id': 'benchmark-input-' + reference['sha256'], 'split': 'training',
                                  'input': value, 'inputs': [{'path': '/work/inputs/value.json', 'source': prepared}]})
                    preparations.append({'source': reference, 'wrapper': prepared, 'encoding': encoding,
                                         'origin': 'host_preparation_from_actual_file'})
                save(directory / 'preparation.json', {'cases': preparations,
                     'scope': 'mechanical_input_wrapping_not_agent_authored_execution_trajectory'})
                library = self._learn(program, cases, directory / 'native', source_evidence,
                                     origin='model_construction', large_output=large_output)
                verify(library)
                native = self._catalog(library, self.owner)
                snapshot = validate_capability_snapshot(native['snapshot'], self.owner)
                if not snapshot['roots']:
                    raise ValueError('benchmark_script_no_native_capability')
                save(directory / 'native-catalog.json', native)
                refs = [source_evidence, *examples, file_ref(directory / 'request.json'),
                        file_ref(directory / 'preparation.json'),
                        file_ref(directory / 'native/observations.json'),
                        file_ref(directory / 'native/certification.json'),
                        file_ref(directory / 'native-catalog.json'),
                        *[row['wrapper'] for row in preparations]]
                material = self.materials.register(backend='script_motif', library=library, refs=refs,
                                                   acquisition_key=key, opportunity=opportunity)
                combined = self.catalog()
                value_ids = {cap['id'] for cap in snapshot['capabilities']
                             if set(cap['contract']['input_schema'].get('properties', {})) == {'value'}}
                outcome.update(status='registered', library=library, material=material, catalog=combined,
                    snapshot=combined['snapshot'], refs=snapshot['roots'],
                    value_refs=[ref for ref in snapshot['roots'] if ref['id'] in value_ids],
                    native_evidence=refs)
            except Exception as error:
                failure = error
                diagnostic, references = _native_failure_feedback(directory, error)
                outcome.update(error=type(error).__name__ + ':' + str(error),
                               diagnostic=diagnostic, evidence_refs=references)
                if isinstance(getattr(error, 'script_diagnostics', None), dict):
                    outcome['script_diagnostics'] = copy.deepcopy(error.script_diagnostics)
                prior_diagnostic = getattr(error, 'evolution_diagnostic', None)
                error.evolution_diagnostic = {**diagnostic, **(prior_diagnostic if isinstance(prior_diagnostic, dict) else {})}
                error.evolution_evidence_refs = references
                raise
            finally:
                save(result_path, outcome)
                if failure is not None:
                    result_ref = file_ref(result_path)
                    failure.evolution_evidence_refs = [*failure.evolution_evidence_refs, result_ref]
                    failure.evolution_diagnostic['result_evidence_id'] = 'evidence_' + result_ref['sha256']
            return outcome

    def execute(self, cap_ref, inputvalue, directory, task_id):
        """Use an original native grant; return the original Runtime trace ref."""
        catalog = self.catalog()
        snapshot = catalog['snapshot']
        if cap_ref not in snapshot['roots']:
            raise ValueError('benchmark_script_capability_not_registered')
        cap = next(cap for cap in snapshot['capabilities'] if cap['id'] == cap_ref['id'])
        if cap['implementation']['kind'] == 'composition':
            arguments = json.loads(verify(inputvalue)) if isinstance(inputvalue, dict) and set(inputvalue) == {
                'path', 'sha256'} else inputvalue
            return self.execute_arguments(cap_ref, arguments, directory, task_id)
        source = None
        if isinstance(inputvalue, dict) and set(inputvalue) == {'path', 'sha256'}:
            source = copy.deepcopy(inputvalue)
            value, encoding = _payload(source)
        else:
            value = copy.deepcopy(inputvalue)
            encoding = 'explicit_run_input_value'
        directory = Path(directory)
        directory.mkdir(parents=True, mode=0o700, exist_ok=False)
        payload = directory / 'input-value.json'
        payload.write_bytes(_canonical_json(value))
        inputs = [{'path': '/work/inputs/value.json', 'source': file_ref(payload)}]
        properties = cap['contract']['input_schema'].get('properties', {})
        args = {'value': value} if set(properties) == {'value'} else {'paths': ['/work/inputs/value.json']}
        save(directory / 'input-provenance.json', {'source': source, 'encoding': encoding,
             'value_file': file_ref(payload), 'scope': 'host_input_binding_to_certified_script'})
        _validate_execution_arguments(cap, args, encoding)
        return self._run(catalog, cap_ref, args, inputs, directory, task_id, source)

    def execute_arguments(self, cap_ref, arguments, directory, task_id, *, inputs=()):
        """Execute an exact original Capability input, including composition slots."""
        catalog = self.catalog()
        if cap_ref not in catalog['snapshot']['roots']:
            raise ValueError('benchmark_script_capability_not_registered')
        capability = next(cap for cap in catalog['snapshot']['capabilities'] if cap['id'] == cap_ref['id'])
        _validate_execution_arguments(capability, arguments, 'explicit_capability_arguments')
        capability_digest(arguments)
        for item in inputs:
            verify(item['source'])
        directory = Path(directory)
        directory.mkdir(parents=True, mode=0o700, exist_ok=False)
        save(directory / 'input-provenance.json', {'source': None,
             'encoding': 'explicit_capability_arguments', 'inputs': list(inputs),
             'scope': 'exact_original_capability_input_no_leaf_wrapper'})
        return self._run(catalog, cap_ref, arguments, list(inputs), directory, task_id, None)

    def _run(self, catalog, cap_ref, args, inputs, directory, task_id, source):
        snapshot = catalog['snapshot']
        trace = self._execute(snapshot, cap_ref, catalog['libraries'], inputs, args, directory, task_id)
        path = directory / 'trace.json'
        if not path.exists():
            save(path, trace)
        if capability_digest(json.loads(path.read_text(encoding='utf-8'))) != capability_digest(trace):
            raise ValueError('benchmark_script_native_trace_changed')
        return {'trace': trace, 'execution_ref': file_ref(path), 'snapshot': snapshot,
                'capability': cap_ref, 'arguments': args, 'source': source,
                'scope': 'actual_native_script_execution_not_semantic_task_quality'}
