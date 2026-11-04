"""Sealed facts survive real UI/global refreshes while semantic changes still revoke them."""
import json
import subprocess
import shutil
from pathlib import Path
import pytest
from src.adapters.ppt_learning_evidence import freeze_state,verify_state_binding,projection,digest

@pytest.fixture
def state_file(tmp_path):
    out=tmp_path/'output';folder=out/'tasks'/('1'*32);folder.mkdir(parents=True)
    state={'task_id':'1'*32,'user_id':'owner','session_id':'session-one','mode':'baseline','status':'completed','scene':'ppt',
           'scene_inputs':[{'name':'论文.pdf','version_sha256':'a'*64}],
           'stats':{'upstream_requests':2,'verified_skips':0,'usage_complete':True,'pending_requests':0}}
    path=folder/'task-state.json';path.write_text(json.dumps(state,ensure_ascii=False))
    return out,folder,path,state

def test_ui_and_global_counters_do_not_invalidate_execution_evidence(state_file):
    out,folder,path,state=state_file
    binding=freeze_state(out,folder,state);original=binding.read_bytes()
    state.update(progress={'message':'刷新'},messages=['later UI projection'])
    state['stats'].update(global_upstream_requests=10000,global_estimated_cost_usd=88.1,active=False)
    path.write_text(json.dumps(state,ensure_ascii=False));verify_state_binding(out,binding)
    assert freeze_state(out,folder,state)==binding and binding.read_bytes()==original

@pytest.mark.parametrize('key,value',[('status','failed'),('user_id','other'),('mode','execute'),('failure','late_failure'),
    ('scene_inputs',[]),('stats',{'upstream_requests':3})])
def test_ownership_source_failure_and_usage_changes_still_revoke(state_file,key,value):
    out,folder,path,state=state_file;binding=freeze_state(out,folder,state)
    state[key]=value;path.write_text(json.dumps(state))
    with pytest.raises(ValueError,match='facts changed'):verify_state_binding(out,binding)

@pytest.mark.skipif(not shutil.which('node'),reason='Node is needed for cross-language fact identity')
def test_python_typescript_use_the_same_projection_and_guard(state_file):
    out,folder,path,state=state_file;binding=freeze_state(out,folder,state)
    root=Path(__file__).resolve().parents[1]
    code="""import {readFileSync} from 'node:fs';
import {pptLearningState,pptLearningStateDigest,verifyPptStateBinding} from './src/adapters/ppt_learning_evidence.ts';
const [output,state,binding]=process.argv.slice(1);verifyPptStateBinding(output,binding);
console.log(pptLearningStateDigest(pptLearningState(JSON.parse(readFileSync(state,'utf8')))));"""
    value=subprocess.check_output(['node','--experimental-strip-types','--input-type=module','-e',code,str(out),str(path),str(binding)],cwd=root,text=True)
    assert value.strip()==digest(projection(state))
