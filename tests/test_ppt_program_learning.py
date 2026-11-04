"""Synthetic lifecycle evidence plus real namespace execution, not cloud savings."""
import json
from pathlib import Path
import shutil
import subprocess
from uuid import UUID

import pytest

from tests.test_web_ppt_learning import owned, task, pair, single, worker, save
from src.adapters.artifact_motif_compiler import digest, sha

SOURCE = '''"""Read the current JSON title and create one text artifact in a fresh output directory."""
import sys,json
from pathlib import Path
d=json.load(open(sys.argv[1]))
out=Path(sys.argv[2]);out.mkdir(parents=True)
(out/'title.txt').write_text(d['title'],encoding='utf-8')
'''


def workspace(directory, index, *, witnessed=False):
    session='session-'+str(UUID(int=int(directory.name,16)))
    work=directory.parent.parent/'sessions'/session/'work'
    for name in ('inputs','code','outputs/code','command-tmp'):(work/name).mkdir(parents=True,exist_ok=True)
    content=work/'inputs/current.json';content.write_text(json.dumps({'title':f'Independent diagnostic content {index}'}))
    save(work/'approved-inputs.json',{'files':{'current.json':sha(content.read_bytes())}})
    effective=worker.read(directory/'effective-config.json')
    effective.update(workspace=str(work),session_id=session,scene_options={'allow_output':True},rsi=effective['mode']=='execute');save(directory/'effective-config.json',effective)
    for name in ('task-state.json','task.json'):
        value=worker.read(directory/name);value.update(session_id=session,rsi=effective['rsi']);save(directory/name,value)
    if witnessed:
        source=work/'code/render.py';source.write_text(SOURCE)
        output=work/'outputs/code/first';output.mkdir();(output/'title.txt').write_text(f'Independent diagnostic content {index}')
        arguments={'command':'python3 /work/render.py /work/inputs/current.json /work/outputs/first','description':'Current title export'}
        events=[{'type':'tool/call','data':{'callId':'native-program','name':'bash','arguments':arguments}},
                {'type':'tool/result','data':{'message':{'content':[{'type':'tool-result','toolCallId':'native-program','isError':False,
                    'content':[{'type':'text','text':'[exit code: 0]'}]}]}}}]
        with (directory/'events.jsonl').open('a') as stream:stream.write(''.join(json.dumps(r)+'\n' for r in events))
        before={'code/render.py':{'sha256':sha(source.read_bytes())},'inputs/current.json':{'sha256':sha(content.read_bytes())}}
        save(directory/'reuse-boundaries.jsonl',{'call_id':'native-program','arguments_sha256':digest(arguments),'is_error':False,
             'before':{'files':before,'complete':True},'after':{'files':{**before,'outputs/code/first/title.txt':{'sha256':sha((output/'title.txt').read_bytes())}},'complete':True}})
    else:(directory/'reuse-boundaries.jsonl').write_text('')
    return work


def prepare(owned,*,singles=False,source_mode='baseline'):
    if singles:(owned[0]/'comparisons.json').unlink()
    for n in (1,2):
        directory=task(owned,n,mode=source_mode)
        workspace(directory,n,witnessed=True)
        if singles:single(owned,directory)
        else:pair(owned,n,directory,review=False)
    worker.advance(owned[2])
    return worker.read(owned[1]/'program-selected.json')


@pytest.mark.skipif(not shutil.which('bwrap'),reason='real namespace certification requires Linux bubblewrap')
@pytest.mark.parametrize('regression',[False,True])
@pytest.mark.parametrize('source_kind',['paired_baseline','single_baseline','single_execute'])
def test_program_from_tasks_certifies_then_future_actual_executions_require_lower_full_cost(owned,regression,source_kind):
    singles=source_kind!='paired_baseline'
    selected=prepare(owned,singles=singles,source_mode='execute' if source_kind=='single_execute' else 'baseline')
    assert selected['phase']=='probation'
    out,store,req=owned
    library=store/selected['library'];program=worker.read(library)['programs'][0]
    assert program['certification']['distinct_inputs']==2 and program['certification']['semantic_quality_accepted'] is False
    if singles:
        assert not (owned[0]/'comparisons.json').exists()
        assert all(t.startswith('single-') for t in selected['support_turns'])
        save(owned[0]/'comparisons.json',{'version':1,'principal':'diagnostic-user','turns':[]})
    before=worker.sha(library);worker.advance(req);assert worker.sha(library)==before
    for n in (3,4):
        baseline=task(owned,n*10,source=n,cost=.003)
        optimized=task(owned,n*10+1,source=n,mode='execute',cost=.004 if regression else .001)
        work=workspace(optimized,n)
        save(optimized/'ppt-program-snapshot.json',{**selected,'library':str(library)})
        audit=optimized/'artifact-motif-audit.jsonl'
        state=worker.read(optimized/'task-state.json');state['status']='running';save(optimized/'task-state.json',state)
        code="""import {appendFileSync,writeFileSync,mkdtempSync} from 'node:fs';
import {join} from 'node:path';import {request} from 'node:http';
import {startCommandBroker} from './src/adapters/geneloop_command_broker.ts';
import {createPptLearning} from './src/adapters/harless_ppt_learning.ts';
import {loadArtifactLibrary,provideArtifactPrograms,registerArtifactContext,artifactInvocation,runArtifactProgram} from './src/adapters/artifact_motif_runtime.ts';
const [libraryPath,workspace,auditPath,output,taskId,session]=process.argv.slice(1);const library=loadArtifactLibrary(libraryPath);
if(!createPptLearning({output,user:'diagnostic-user',scope:'a'.repeat(64),python:process.env.SSS_PYTHON,taskIds:()=>[]}).program())throw Error('next-task program was not admitted');
const audit=row=>appendFileSync(auditPath,JSON.stringify(row)+'\\n');
registerArtifactContext(session,provideArtifactPrograms({library,workspace,taskId,allowOutput:true,resources:{},audit,auditPath}));
const command='geneloop-recipe '+JSON.stringify({id:library.programs[0].id,inputs:['/work/inputs/current.json'],output:'/work/outputs/new'});
const {audit:ignored,...job}=artifactInvocation(session,command);
const file=join(mkdtempSync(join(workspace,'command-tmp/artifact-job-')),'job.json');
writeFileSync(file,JSON.stringify({...job,bound:job.bound.map(b=>({...b,data:b.data.toString('base64')}))}));
const broker=await startCommandBroker({output,python:process.env.SSS_PYTHON,node:process.execPath,resources:{}});
try{await new Promise((resolve,reject)=>{
 const memberFile='/app/.local/web'+file.slice(output.length);
 const body=JSON.stringify({operation:'run',session,file:memberFile});const req=request({socketPath:broker.socketPath,path:'/artifact',method:'POST',headers:{'Content-Type':'application/json'}},res=>{
  let text='';res.setEncoding('utf8');res.on('data',b=>text+=b);res.on('end',()=>{if(res.statusCode!==200||!text.trim().split('\\n').map(JSON.parse).some(r=>r.exit===0))reject(Error('broker failed: '+text));else resolve();});});req.on('error',reject);req.end(body);
 });}finally{broker.close();}"""
        subprocess.run(['node','--experimental-strip-types','--input-type=module','-e',code,str(library),str(work),str(audit),str(out),optimized.name,state['session_id']],cwd=worker.ROOT,check=True,capture_output=True,text=True)
        state['status']='completed';save(optimized/'task-state.json',state)
        pair(owned,n,baseline,optimized,review=False)
        worker.advance(req)
        if regression:
            assert worker.read(store/'program-selected.json')['phase']=='disabled'
            assert worker.read(store/'program-status.json')['blocked'][0]['reason']=='program_full_cost_regression'
            return
        assert worker.read(store/'program-selected.json')['phase']==('probation' if n==3 else 'active')
    evaluation=worker.read(library.parent/'evaluation.json')
    assert len(evaluation['pairs'])==2 and evaluation['quality_cost_promoted'] is False
    assert all(p['verified_skips_attributed_to_program']==0 and p['program_reuses']==1 for p in evaluation['pairs'])
    assert worker.read(store/'program-status.json')['extra_provider_requests']==0


def test_missing_pre_call_program_evidence_never_generates_a_tool(owned):
    for n in (1,2,3):pair(owned,n,task(owned,n),review=False)
    worker.advance(owned[2])
    assert not (owned[1]/'program-selected.json').exists()
    assert worker.read(owned[1]/'program-status.json')['status']=='waiting_for_independent_program_evidence'


def test_same_parent_followups_cannot_supply_independent_program_certification(owned):
    for n in (1,2):
        directory=task(owned,n);workspace(directory,n,witnessed=True)
        pair(owned,n,directory,review=False)
    path=owned[0]/'comparisons.json';journal=worker.read(path)
    for turn in journal['turns']:turn['session_id']='session-one-editable-draft'
    save(path,journal);worker.advance(owned[2])
    assert not (owned[1]/'program-selected.json').exists()
    assert worker.read(owned[1]/'program-status.json')['status']=='waiting_for_independent_program_evidence'


@pytest.mark.skipif(not shutil.which('bwrap'),reason='real namespace certification requires Linux bubblewrap')
def test_program_certification_requires_independent_current_input_and_keeps_failures(owned):
    for n in (1,2):
        directory=task(owned,n,source=1,question='same task')
        workspace(directory,1,witnessed=True)
        pair(owned,n,directory,review=False)
    worker.advance(owned[2])
    assert not (owned[1]/'program-selected.json').exists()


@pytest.mark.skipif(not shutil.which('bwrap'),reason='real namespace certification requires Linux bubblewrap')
def test_persistent_program_is_disabled_when_its_source_feedback_is_withdrawn(owned):
    prepare(owned)
    p=owned[0]/'comparisons.json';value=worker.read(p);value['turns'][0]['lanes']['baseline']['feedback']='down';save(p,value)
    worker.advance(owned[2])
    assert worker.read(owned[1]/'program-selected.json')['phase']=='disabled'


@pytest.mark.skipif(not shutil.which('bwrap'),reason='real namespace certification requires Linux bubblewrap')
@pytest.mark.parametrize('member_alias', [False, True])
@pytest.mark.parametrize('single_execute',[False,True])
def test_certification_uses_the_existing_account_broker_protocol(owned, member_alias,single_execute):
    pointer=prepare(owned,singles=single_execute,source_mode='execute' if single_execute else 'baseline');out,store,_=owned
    original=(store/pointer['library']).parent/'candidates.json'
    folder=store/('program-'+'f'*24);folder.mkdir()
    raw=original.read_text()
    if member_alias:
        raw=raw.replace(str(out), '/app/.local/web')
    (folder/'candidates.json').write_text(raw)
    code="""import {request} from 'node:http';import {startCommandBroker} from './src/adapters/geneloop_command_broker.ts';
const [output,file]=process.argv.slice(1);const broker=await startCommandBroker({output,node:process.execPath,python:process.env.SSS_PYTHON,resources:{}});
try{await new Promise((resolve,reject)=>{const req=request({socketPath:broker.socketPath,path:'/artifact',method:'POST'},res=>{
 let text='';res.setEncoding('utf8');res.on('data',s=>text+=s);res.on('end',()=>{if(res.statusCode!==200||!text.trim().split('\\n').map(JSON.parse).some(r=>r.exit===0))reject(Error(text));else resolve();});});
 req.on('error',reject);req.end(JSON.stringify({operation:'certify',file}));});}finally{broker.close();}"""
    request_file=str(folder/'candidates.json')
    if member_alias:
        request_file='/app/.local/web'+request_file[len(str(out)):]
    subprocess.run(['node','--experimental-strip-types','--input-type=module','-e',code,str(out),request_file],cwd=worker.ROOT,check=True,capture_output=True,text=True)
    assert worker.read(folder/'library.json')['programs'][0]['certification']['distinct_inputs']==2
