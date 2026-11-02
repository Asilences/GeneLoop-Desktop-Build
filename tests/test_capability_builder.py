"""Offline proposal/dataflow diagnostics; proposals are synthetic fixtures."""
import copy
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from src.adapters.capability_builder import compile_proposal
from src.adapters.capability_contract import create_capability, create_capability_snapshot, capability_ref
from tests.test_capability_contract import leaf

SCALAR = {'type': 'integer'}
RECORD = {'type': 'object', 'properties': {'value': SCALAR}, 'required': ['value'], 'additionalProperties': False}


def setup():
    definition=leaf()
    definition={k:definition[k] for k in ('owner','contract','implementation','dependencies')}
    definition['contract']={'input_schema':RECORD,'output_schema':RECORD,'effects':['read']}
    a=create_capability(definition)
    definition=copy.deepcopy(definition);definition['implementation']['legacy_ref']['object_id']='second'
    b=create_capability(definition)
    snapshot=create_capability_snapshot('owner',[capability_ref(a),capability_ref(b)],[a,b])
    proposal={'format':'capability_compose_proposal_v1','owner':'owner','contract':{'input_schema':RECORD,'output_schema':RECORD,'effects':['read']},
        'steps':[{'id':'first','capability':capability_ref(a),'arguments':{'kind':'input','path':[]}},
                 {'id':'second','capability':capability_ref(b),'arguments':{'kind':'object','fields':{'value':{'kind':'step','step_id':'first','path':['value']}}}}],
        'output':{'kind':'step','step_id':'second','path':[]}}
    return snapshot,proposal


class BuilderTests(unittest.TestCase):
    def test_two_generations_and_candidate_boundary(self):
        snapshot,proposal=setup(); original=copy.deepcopy(snapshot)
        first=compile_proposal(proposal,snapshot,'owner'); c=first['capability']
        second=copy.deepcopy(proposal); second['steps']=[{'id':'next','capability':capability_ref(c),'arguments':{'kind':'input','path':[]}}]; second['output']={'kind':'step','step_id':'next','path':[]}
        result=compile_proposal(second,first['snapshot'],'owner')
        self.assertEqual(len(result['snapshot']['capabilities']),4)
        self.assertEqual(snapshot,original)
        for candidate in [c,result['capability']]:
            self.assertEqual(candidate['certification'],'candidate');self.assertEqual(candidate['lifecycle'],'build_only')
        # Prior closure is retained but not automatically made visible for new calls.
        hidden=copy.deepcopy(second);hidden['steps'][0]['capability']=proposal['steps'][0]['capability']
        with self.assertRaisesRegex(ValueError,'reference_not_visible'): compile_proposal(hidden,first['snapshot'],'owner')

    def test_static_dataflow_and_schema_failures(self):
        snapshot,proposal=setup()
        def incompatible(x): x['steps'][1]['arguments']['fields']['value']={'kind':'literal','value':'not a number'}
        def absent(x): x['steps'][1]['arguments']['fields']['value']['path']=['missing']
        def future(x): x['steps'][0]['arguments']={'kind':'step','step_id':'second','path':[]}
        def owner(x): x['owner']='other'
        def authority(x): x['certification']='certified'
        def missing(x): x['steps'][1]['arguments']['fields']={}
        def unknown(x): x['steps'][0]['capability']['sha256']='0'*64
        def output(x): x['contract']['output_schema']={'type':'string'}
        for mutate in [incompatible,absent,future,owner,authority,missing,unknown,output]:
            bad=copy.deepcopy(proposal);mutate(bad)
            with self.assertRaises(ValueError):compile_proposal(bad,snapshot,'owner')
        optional=copy.deepcopy(proposal);optional['contract']['input_schema']['required']=[]
        with self.assertRaisesRegex(ValueError,'schema_incompatible'):compile_proposal(optional,snapshot,'owner')

    def test_negative_zero_proposal_rejected_before_wire_export(self):
        snapshot,proposal=setup()
        proposal['steps'][0]['arguments']={'kind':'object','fields':{'value':{'kind':'literal','value':-0.0}}}
        with self.assertRaisesRegex(ValueError,'negative_zero'):
            compile_proposal(proposal,snapshot,'owner')

    def test_effects_and_archived_dependencies(self):
        snapshot,proposal=setup()
        bad=copy.deepcopy(proposal);bad['contract']['effects']=['workspace_write']
        with self.assertRaisesRegex(ValueError,'effects_underdeclared'):compile_proposal(bad,snapshot,'owner')
        changed=copy.deepcopy(snapshot['capabilities']);changed[0]['lifecycle']='archived'
        snapshot=create_capability_snapshot('owner',snapshot['roots'],changed)
        with self.assertRaisesRegex(ValueError,'dependency_unavailable'):compile_proposal(proposal,snapshot,'owner')

    def test_array_binding_and_precise_specialization(self):
        snapshot,proposal=setup()
        parent=snapshot['capabilities'][0]
        definition={k:copy.deepcopy(parent[k]) for k in ('owner','contract','implementation','dependencies')}
        array={'type':'array','items':{'type':'integer'}}
        definition['contract']={'input_schema':array,'output_schema':array,'effects':['read']}
        primitive=create_capability(definition)
        snapshot=create_capability_snapshot('owner',[capability_ref(primitive)],[primitive])
        proposal['contract']={'input_schema':RECORD,'output_schema':array,'effects':['read']}
        proposal['steps']=[{'id':'specialized','capability':capability_ref(primitive),'arguments':{'kind':'array','items':[{'kind':'literal','value':1},{'kind':'input','path':['value']}]}}]
        proposal['output']={'kind':'step','step_id':'specialized','path':[]}
        built=compile_proposal(proposal,snapshot,'owner')
        self.assertEqual(built['capability']['dependencies'],[capability_ref(primitive)])
        proposal['steps'][0]['arguments']['items'][0]['value']='bad'
        with self.assertRaisesRegex(ValueError,'literal_schema'):compile_proposal(proposal,snapshot,'owner')

    def test_literal_array_object_bindings_and_cli(self):
        snapshot,proposal=setup()
        proposal['steps'][0]['arguments']={'kind':'object','fields':{'value':{'kind':'literal','value':3}}}
        compiled=compile_proposal(proposal,snapshot,'owner')
        self.assertEqual(compiled['capability']['certification'],'candidate')
        with tempfile.TemporaryDirectory() as directory:
            root=Path(directory)
            for name,value in [('proposal',proposal),('snapshot',snapshot)]: (root/(name+'.json')).write_text(json.dumps(value))
            command=[sys.executable,'scripts/build-capability.py','--proposal',str(root/'proposal.json'),'--construction-snapshot',str(root/'snapshot.json'),'--owner','owner','--output',str(root/'result.json')]
            first=subprocess.run(command,capture_output=True,text=True)
            self.assertEqual(first.returncode,0,first.stderr); self.assertEqual(json.loads((root/'result.json').read_text()),compiled)
            self.assertNotEqual(subprocess.run(command,capture_output=True).returncode,0)

if __name__=='__main__':unittest.main()
