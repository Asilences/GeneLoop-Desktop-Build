"""Function ABI admission diagnostics; candidate source is never run on host."""
import pytest
import os,sys,json
from pathlib import Path
from scenarios.paper_proofreading.frontier.learn import executable_source
from src.adapters.script_motif_compiler import compile_script


def test_host_encodes_json_IO_and_preserves_the_model_function_body():
    source="def run(value):\n    return {'count':len(value['rows'])}\n"
    program={'source':source,'mode':'json','interface':'function_v1'}
    full=executable_source(program,[{'inputs':[{'path':'/work/inputs/value.json'}]}])
    assert full.startswith(source)
    compiled=compile_script(full,{'/work/inputs/value.json':{'suffix':'.json','format':'json','shape':{'object':{}}}})
    assert len(compiled['inputs'])==1 and '__MOTIF_INPUT_0__' in compiled['template']


def test_path_roles_are_bound_by_the_host_without_model_argv_or_literal_paths():
    program={'source':"import zipfile\ndef run(paths):\n    return {'count':len(zipfile.ZipFile(paths['before']).namelist())}\n",'mode':'paths','interface':'function_v1'}
    cases=[{'inputs':[{'path':'/work/inputs/before.zip'},{'path':'/work/inputs/after.zip'}]}]
    full=executable_source(program,cases)
    compiled=compile_script(full,{item['path']:{'suffix':'.zip','format':'zip'} for item in cases[0]['inputs']})
    assert len(compiled['inputs'])==2


@pytest.mark.parametrize('source',["def run(a,b):\n return {}", "def other(a):\n return {}", "def run(a):\n return {}\nprint('extra')", "frontier_bridge_input={}\ndef run(a):\n return a"])
def test_invalid_entrypoints_or_bridge_shadowing_fail_before_execution(source):
    with pytest.raises(ValueError):executable_source({'source':source,'mode':'json','interface':'function_v1'},[{'inputs':[{'path':'/work/inputs/value.json'}]}])


native=(sys.platform=='linux' and Path('/usr/bin/bwrap').exists() and os.environ.get('RUN_SCRIPT_CAPABILITY_SANDBOX')=='1')
@pytest.mark.skipif(not native,reason='explicit Linux native sandbox diagnostic')
@pytest.mark.parametrize('mode',['json','paths'])
def test_function_entrypoint_is_actually_sandboxed_and_certified_on_distinct_inputs(tmp_path,mode):
    from scenarios.paper_proofreading.frontier.learn import learn
    from src.adapters.capability_scene import reference
    cases=[]
    for i in range(2):
        inputs=[]
        for role in (['value'] if mode=='json' else ['before','after']):
            path=tmp_path/(f'{role}-{i}'+('.json' if mode=='json' else '.txt'))
            path.write_text(json.dumps({'rows':list(range(i+1))},separators=(',',':')) if mode=='json' else role+str(i),encoding='utf-8')
            inputs.append({'path':'/work/inputs/'+role+path.suffix,'source':reference(path)})
        cases.append({'id':'diagnostic-'+str(i),'inputs':inputs})
    source=("def run(value):\n    return {'count':len(value['rows'])}\n" if mode=='json' else
        "import hashlib\ndef run(paths):\n    return {k:hashlib.sha256(open(p,'rb').read()).hexdigest() for k,p in paths.items()}\n")
    program={'source':source,'mode':mode,'interface':'function_v1','description':'Host fixture function ABI diagnostic, not model quality evidence'}
    output=tmp_path/'native';library=learn(program,cases,output,reference(__file__),large_output=True,origin='host_diagnostic')
    value=json.loads(Path(library['path']).read_text())
    assert len(value['programs'])==1 and value['programs'][0]['certification']['passed']
    rows=json.loads((output/'observations.json').read_text());witness=rows[1]['candidates'][0]['witness']
    assert witness['program_interface']=='function_v1' and witness['input_evidence_scope'].startswith('host_diagnostic')
    assert witness['model_source_sha256']!=witness['executed_source_sha256']
