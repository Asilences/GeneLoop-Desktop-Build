"""Synthetic contract diagnostics; no model behavior or effectiveness claim."""
import copy
import hashlib
import json
import unittest
import subprocess
from pathlib import Path
from src.adapters.capability_contract import (capability_digest, capability_ref, create_capability,
    create_capability_snapshot, validate_capability, validate_capability_snapshot, map_legacy_library)
from src.adapters.script_motif_compiler import digest


def leaf(name='a', owner='owner'):
    return create_capability({'owner': owner, 'contract': {'input_schema': {'type': 'object'}, 'output_schema': {'type': 'object'}, 'effects': ['read']},
        'implementation': {'kind': 'legacy', 'legacy_ref': {'backend': 'source_program', 'object_id': name,
            **{k: hashlib.sha256(name.encode()).hexdigest() for k in ('library_sha256', 'library_digest', 'object_sha256', 'certificate_sha256')}}}, 'dependencies': []})


def compose(children):
    return create_capability({'owner': 'owner', 'contract': {'input_schema': {'type': 'object'}, 'output_schema': {'type': 'object'}, 'effects': ['read']},
        'implementation': {'kind': 'composition', 'steps': [{'id': 'step'+str(i), 'capability': capability_ref(c), 'arguments': {'kind': 'input', 'path': []}} for i,c in enumerate(children)],
            'output': {'kind': 'step', 'step_id': 'step'+str(len(children)-1), 'path': []}}, 'dependencies': [capability_ref(c) for c in children]})


def legacy_fixture(backend):
    if backend == 'source_program':
        identity = {'format': 'parameterized_source_program_v1', 'language': 'javascript', 'template': 'const x=__GENELOOP_PARAMETERS__;', 'parameters_schema': {'type': 'object'}}
        sha = digest(identity)
        p = {**identity, 'id': 'source_'+sha[:24], 'status': 'certified', 'certification': {'program_identity': sha, 'source_equivalent': True}}
        body = {'format': 'source_program_library_v1', 'programs': [p]}
    else:
        identity = {'version': 1, 'source': 'print(1)', 'inputs': [], 'dependencies': [], 'input_argument_indices': [], 'output_argument_index': 0, 'argument_count': 1, 'language': 'python', 'execution_policy': 'fresh_output_network_disabled_v1'}
        sha = digest(identity)
        p = {**identity, 'id': 'artifact_'+sha[:24], 'source_sha256': hashlib.sha256(identity['source'].encode()).hexdigest(), 'certification': {'program_sha256': sha, 'source_equivalent': True, 'passed': True, 'distinct_inputs': 2}}
        body = {'kind': 'witnessed_artifact_program_library', 'version': 1, 'programs': [p]}
    body['elapsed_seconds'] = 1.25
    raw = json.dumps({**body, 'digest': digest(body)}, ensure_ascii=False, indent=2).encode()
    return raw, hashlib.sha256(raw).hexdigest()


class CapabilityTests(unittest.TestCase):
    def test_numeric_unicode_canonical(self):
        self.assertEqual(capability_digest({'x': 1.25, '\U00010000': 2, '\ue000': 3}), '5c2c01fd25da0325635a9dbf7256ed32fa3d65384982fb59cfa2cc0d23e63795')
        self.assertEqual(capability_digest([1, 0]), capability_digest([1.0, -0.0]))
        for value in [float('inf'), float('nan'), 9007199254740992, '\ud800']:
            with self.assertRaises(ValueError): capability_digest(value)

    def test_online_schema_dialect_positive_and_negative_cases(self):
        cases=json.loads((Path(__file__).parent/'fixtures/capability_dialect_cases.json').read_text())
        for case in cases:
            definition={k:copy.deepcopy(leaf()[k]) for k in ('owner','contract','implementation','dependencies')}
            definition['contract']['input_schema']=case['schema']
            with self.subTest(case=case['name']):
                if case['accepted']:
                    self.assertEqual(create_capability(definition)['contract']['input_schema'],case['schema'])
                else:
                    with self.assertRaises(ValueError):create_capability(definition)

    def test_native_source_admission_and_mapping_agree(self):
        fixtures=subprocess.run(['node','--experimental-strip-types','tests/fixtures/capability_native_validation.mjs'],capture_output=True,text=True)
        self.assertEqual(fixtures.returncode,0,fixtures.stderr)
        for case in json.loads(fixtures.stdout):
            with self.subTest(case=case['name']):
                if case['native_accepted']:
                    result=map_legacy_library(case['raw'],'owner','source_program',case['sha'])
                    self.assertEqual(len(result),1)
                    self.assertEqual(result[0]['certification'],'candidate')
                    self.assertEqual(result[0]['contract']['input_schema']['required'],['x','x'])
                else:
                    with self.assertRaisesRegex(ValueError,'source_program_changed'):
                        map_legacy_library(case['raw'],'owner','source_program',case['sha'])

    def test_identity_binds_contract_owner_and_excludes_states(self):
        a = leaf()
        b = copy.deepcopy(a); b.update(lifecycle='archived', certification='rejected', migration='promoted')
        self.assertEqual(capability_ref(a), capability_ref(b))
        for change in [('owner', 'foreign'), ('contract', {'input_schema': {'type': 'string'}, 'output_schema': {}, 'effects': ['read']})]:
            c = copy.deepcopy(a); c[change[0]] = change[1]
            with self.assertRaises(ValueError): validate_capability(c)
        with self.assertRaises(ValueError): validate_capability(a, 'foreign')

    def test_recursive_snapshot_and_failures(self):
        a,b = leaf(),leaf('b'); c = compose([a,b]); d = compose([c])
        s = create_capability_snapshot('owner', [capability_ref(d)], [a,b,c,d])
        self.assertEqual(validate_capability_snapshot(s), s)
        checked = validate_capability_snapshot(s); checked['capabilities'][0]['owner']='changed'
        self.assertEqual(s['owner'], 'owner')
        cases = [dict(s, capabilities=s['capabilities'][:-1]), dict(s, capabilities=s['capabilities']+[a]), dict(s, roots=s['roots']*2), dict(s, owner='foreign'), dict(s,digest='0'*64)]
        for broken in cases:
            with self.assertRaises(ValueError): validate_capability_snapshot(broken)
        with self.assertRaisesRegex(ValueError, 'extra_capability'): create_capability_snapshot('owner', [capability_ref(a)], [a,b])
        with self.assertRaisesRegex(ValueError, 'foreign_owner'): create_capability_snapshot('owner', [capability_ref(a)], [a,leaf('b','foreign')])
        changed = copy.deepcopy(c); changed['implementation']['steps'][0]['arguments']={'kind':'step','step_id':'step1','path':[]}
        with self.assertRaisesRegex(ValueError, 'unavailable'): validate_capability(changed)
        changed=copy.deepcopy(c); changed['dependencies'].append(changed['dependencies'][0])
        with self.assertRaises(ValueError): validate_capability(changed)

    def test_native_legacy_digest_is_authoritative_for_python_mapping(self):
        result=subprocess.run(['node','--experimental-strip-types','tests/fixtures/capability_legacy_native.mjs'],capture_output=True,text=True)
        self.assertEqual(result.returncode,0,result.stderr)
        native=json.loads(result.stdout)
        self.assertEqual(map_legacy_library(native['raw'],'owner','source_program',native['sha']),native['mapped'])
        self.assertIn('1.0',native['raw']);self.assertIn('0.1',native['raw'])
        # A library rehashed solely with Python's 1.0 spelling is already invalid
        # to the authoritative native runtime; both bridge and TS must reject it.
        raw,_=legacy_fixture('source_program');library=json.loads(raw)
        library['elapsed_seconds']=1.0
        library['digest']=digest({k:v for k,v in library.items() if k!='digest'})
        encoded=json.dumps(library).encode()
        with self.assertRaisesRegex(ValueError,'legacy_library_invalid'):
            map_legacy_library(encoded,'owner','source_program',hashlib.sha256(encoded).hexdigest())

    def test_legacy_bytes_and_certificates_retained(self):
        for backend in ['source_program', 'artifact_motif']:
            raw,sha=legacy_fixture(backend); original=bytes(raw); p=json.loads(raw)['programs'][0]
            mapped=map_legacy_library(raw,'owner',backend,sha)[0]; ref=mapped['implementation']['legacy_ref']
            self.assertEqual(raw,original); self.assertEqual(ref['object_id'],p['id']); self.assertEqual(ref['certificate_sha256'],digest(p['certification']))
            self.assertEqual(mapped['certification'],'candidate'); self.assertEqual(mapped['lifecycle'],'build_only')
            with self.assertRaisesRegex(ValueError,'bytes_changed'): map_legacy_library(raw+b' ','owner',backend,sha)
            bad=json.loads(raw); bad['programs'][0]['certification']['source_equivalent']=False; bad['digest']=digest({k:v for k,v in bad.items() if k!='digest'})
            badraw=json.dumps(bad).encode()
            with self.assertRaisesRegex(ValueError,'certificate_missing'): map_legacy_library(badraw,'owner',backend,hashlib.sha256(badraw).hexdigest())


if __name__ == '__main__': unittest.main()
