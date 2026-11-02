"""Paper checker and full native lifecycle diagnostics, with synthetic BibTeX.

The Linux test uses the original compiler/certifier and real sandbox. Its
composition proposal is deliberately deterministic, not model/RSI evidence.
"""
import copy
import hashlib
import json
import os
from pathlib import Path
import subprocess
import sys
import pytest
from src.adapters.capability_contract import capability_digest
from src.adapters.capability_scene import load_scene_adapter,reference
from src.adapters.capability_improvement import run_improvement
from src.adapters.capability_builder import compile_proposal
from scenarios.paper_proofreading.verify_capability_outputs import verify
ROOT=Path(__file__).resolve().parents[1]


def put(path,value):
    path.write_text(json.dumps(value,ensure_ascii=False), encoding='utf-8');return reference(path)


def case(tmp_path):
    (tmp_path/'inputs').mkdir()
    raw=b'@article{A,title={First}}\n@article{A,title={Second}}\n@book{B,title={Third}}\n'
    (tmp_path/'inputs/a.bib').write_bytes(raw)
    manifest={'workspace':str(tmp_path),'owner':'owner','task_id':'t','inputs':[{'path':'/work/inputs/a.bib','sha256':hashlib.sha256(raw).hexdigest()}]}
    trace={'owner':'owner','task_id':'t','status':'succeeded','input_versions':manifest['inputs'],
           'result':{'entry_count':3,'unique_key_count':2,'duplicate_keys':['A']}}
    spec={'kind':'bibtex_inventory_v1','source_path':'/work/inputs/a.bib','fields':{k:[k] for k in trace['result']}}
    return manifest,trace,spec


def test_checker_recomputes_duplicate_records_and_detects_wrong_final_counts(tmp_path):
    manifest,trace,spec=case(tmp_path)
    assert verify(manifest,trace,spec)['passed']
    trace['result']['unique_key_count']=3
    verdict=verify(manifest,trace,spec)
    assert not verdict['passed'] and verdict['checks'][2]['status']=='failed'


def test_checker_does_not_accept_boolean_counts_or_input_version_changes(tmp_path):
    manifest,trace,spec=case(tmp_path);trace['result']['entry_count']=True
    assert not verify(manifest,trace,spec)['passed']
    (tmp_path/'inputs/a.bib').write_text('changed', encoding='utf-8')
    with pytest.raises(ValueError,match='input_changed'):verify(manifest,trace,spec)


@pytest.mark.skipif(sys.platform!='linux' or os.getenv('RUN_SCRIPT_CAPABILITY_SANDBOX')!='1',reason='Linux native sandbox diagnostic opt-in')
def test_paper_native_certification_composition_publication_and_next_builder(tmp_path):
    from src.adapters.script_motif_compiler import observe
    source="import re, json\nfrom collections import Counter\ns=open('/work/inputs/source.bib').read()\nkeys=re.findall(r'(?m)^\\s*@\\w+\\s*\\{\\s*([^,\\s{}]+)\\s*,',s)\nc=Counter(keys)\nprint(json.dumps({'entry_count':len(keys),'unique_key_count':len(c),'duplicate_keys':sorted(k for k,n in c.items() if n>1)}))"
    command="python3 - <<'DIAGNOSTIC'\n"+source+"\nDIAGNOSTIC"
    rows=[]
    for label,keys in [('heldout',['X','Y','Y']),('source',['A','B'])]:
        work=tmp_path/label
        for part in ('inputs','code','outputs/code','command-tmp'):(work/part).mkdir(parents=True,exist_ok=True)
        (work/'inputs/source.bib').write_text('\n'.join('@article{'+key+',title={Example}}' for key in keys)+'\n', encoding='utf-8')
        script="import {sandboxRun} from './scripts/certify-script-motifs.mjs';process.stdout.write(sandboxRun(process.argv[1],process.argv[2]));"
        stdout=subprocess.check_output(['node','--input-type=module','-e',script,str(work),command],cwd=ROOT,text=True, encoding='utf-8')
        p=observe(command,'diagnostic BibTeX inventory',str(work),stdout,label,'diagnostic-call')
        p['witness']['events_sha256']='0'*64
        rows.append({'task_id':label,'workspace':str(work),'candidates':[p] if label=='source' else []})
    put(tmp_path/'observations.json',rows);native=tmp_path/'native';native.mkdir()
    subprocess.run(['node','scripts/certify-script-motifs.mjs',str(tmp_path/'observations.json'),str(native)],cwd=ROOT,check=True,capture_output=True,text=True, encoding='utf-8')
    catalog=json.loads(subprocess.check_output(['node','scripts/run-script-capability.mjs','--catalog','--library',str(native/'library.json'),'--owner','owner'],cwd=ROOT,text=True, encoding='utf-8'))
    assert len(catalog['capabilities'])==1
    leaf=catalog['capabilities'][0];contract={**leaf['contract'],'output_schema':leaf['contract']['output_schema']['properties']['value']}
    publication={'libraries':[reference(native/'library.json')]}
    for label,keys in [('validation',['P','P','Q','R']),('followup',['S','T','T','U','V'])]:
        path=tmp_path/(label+'.bib');path.write_text('\n'.join('@article{'+key+',title={Example}}' for key in keys)+'\n', encoding='utf-8')
        virtual='/work/inputs/'+path.name
        publication[label]={'id':label,'inputs':[{'path':virtual,'source':reference(path)}],
            'input':{'paths':[virtual]},'specification':{'kind':'bibtex_inventory_v1','source_path':virtual,
            'fields':{k:[k] for k in ('entry_count','unique_key_count','duplicate_keys')}}}
    pubref=put(tmp_path/'publication.json',publication)
    taskref=put(tmp_path/'task.json',{'id':'inventory','instruction':'诊断：组合已认证程序，返回书目盘点','contract':contract})
    job={'id':'inventory','objective':'capability_acquisition','task':taskref,'publication_plan':pubref,
        'observations':[{'task_id':'source','kind':'repeated_structure','split':'training','summary':'原生合成诊断见证','evidence':reference(tmp_path/'observations.json')}]}
    plan={'format':'capability_improvement_plan_v1','id':'paper-native-diagnostic','owner':'owner',
        'seed':put(tmp_path/'seed.json',catalog['snapshot']),'seed_catalog':put(tmp_path/'catalog.json',catalog),
        'store':str(tmp_path/'store'),'ledger_root':str(tmp_path/'unused-ledger'),'output':str(tmp_path/'run'),
        'policy':{'version':'capability_improvement_policy_v1','max_repairs':0},'jobs':[job],
        'scene_adapter':reference(ROOT/'scenarios/paper_proofreading/capability_adapter.py')}
    adapter=load_scene_adapter(plan)
    def propose(task,library,attempt,parent,feedback):
        attempt.mkdir()
        proposal={'format':'capability_compose_proposal_v1','owner':'owner','contract':contract,
            'steps':[{'id':'inventory','capability':catalog['roots'][0],'arguments':{'kind':'input','path':[]}}],
            'output':{'kind':'step','step_id':'inventory','path':['value']}}
        put(attempt/'candidate.json',compile_proposal(proposal,library['snapshot'],'owner'))
        result={'status':'compiled_candidate','observed_model_usd':None,'diagnostic_only':True}
        put(attempt/'result.json',result);return result
    adapter.construct=propose
    result=run_improvement(plan,adapter,execute=True)
    assert result['status']=='completed',result
    assert result['outcomes'][0]['status']=='published',result
    assert result['outcomes'][0]['capability'] in adapter.library()['snapshot']['roots']
    assert any(f['stage']=='construction' and f['status']=='passed' for f in adapter.feedback.read()['facts'].values())
    assert not Path(plan['ledger_root']).exists()


def test_paper_acquisition_requires_explicit_route_and_partition(tmp_path):
    # Guard diagnostics only; no fixed provider or fabricated model response.
    from scenarios.paper_proofreading.capability_adapter import PaperCapabilityAdapter
    adapter=object.__new__(PaperCapabilityAdapter);adapter.plan={'owner':'owner'}
    assert adapter.acquire({}, {'construction_gap':{'reason':'missing_primitive'}},tmp_path)['status']=='deferred'
    route={'format':'paper_script_learning_routes_v1','owner':'owner','routes':[{'scope':'inventory','backend':'script_motif',
        'tasks':[{'path':'never-read','role':'training'}]}]}
    adapter.plan['learning_routes']=put(tmp_path/'routes.json',route)
    with pytest.raises(ValueError,match='partition_invalid'):
        adapter.acquire({'execution_scope':'inventory'}, {'construction_gap':{'reason':'missing_primitive'}},tmp_path)
