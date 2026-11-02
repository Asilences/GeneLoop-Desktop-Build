"""Transport/permission diagnostics; no model calls or effect claims."""
import asyncio,copy,hashlib,importlib.util,json
from pathlib import Path
import pytest
from scenarios.remotion_edit.web_programs import PublishedPrograms,from_environment

ROOT=Path(__file__).resolve().parents[1]

def fake_runtime(tmp_path):
    source='export const example = 1;'
    policy={'digest':'policy-v1','library_digest':'library-v1','form':{'representation':'typed_tools',
        'library_scope':'all','parameter_binding':'defaults','tool_naming':'description','program_evidence':'source'}}
    state={'policy':policy,'library_path':str(tmp_path/'source-library.json'),'pointer_sha256':'pointer-v1'}
    calls=[]
    def request(value):
        calls.append(copy.deepcopy(value))
        if value['operation']=='resolve_form':return copy.deepcopy(state)
        if value['operation']=='catalog':return {'digest':'library-v1','programs':[]}
        return {'source':source,'source_sha256':hashlib.sha256(source.encode()).hexdigest(),
            'program_id':value['program_id'],'library_digest':'library-v1','parameters':value['parameters'],
            'parameters_sha256':'parameters','supplied_parameters_sha256':'parameters','parameter_binding':'defaults'}
    return state,calls,request

def test_published_program_revalidates_owner_and_freezes_pointer(tmp_path):
    state,calls,request=fake_runtime(tmp_path)
    programs=PublishedPrograms(str(tmp_path),'owner',request)
    result=programs.materialize('source_test',{'title':'CURRENT'})
    assert result['parameters']=={'title':'CURRENT'}
    assert all(c.get('owner')=='owner' for c in calls if c['operation']=='resolve_form')
    assert next(c for c in calls if c['operation']=='catalog')['include_source'] is True
    state['policy']['digest']='policy-v2'
    with pytest.raises(Exception,match='changed'):programs.materialize('source_test',{})

def test_program_materialization_rejects_changed_library_before_execution(tmp_path):
    state,calls,request=fake_runtime(tmp_path)
    def changed(value):
        result=request(value)
        if value['operation']=='materialize':result['library_digest']='other-library'
        return result
    programs=PublishedPrograms(str(tmp_path),'owner',changed)
    with pytest.raises(Exception,match='materialization changed'):programs.materialize('source_test',{})

def test_program_adapter_rejects_incomplete_or_unsupported_configuration(tmp_path,monkeypatch):
    monkeypatch.delenv('GENELOOP_VIDEO_MOTIF_STORE',raising=False)
    monkeypatch.delenv('GENELOOP_VIDEO_MOTIF_OWNER',raising=False)
    assert from_environment() is None
    monkeypatch.setenv('GENELOOP_VIDEO_MOTIF_STORE',str(tmp_path))
    with pytest.raises(Exception,match='incomplete'):from_environment()
    state,calls,request=fake_runtime(tmp_path);state['policy']['form']['library_scope']='lexical_top1'
    with pytest.raises(Exception,match='not supported'):PublishedPrograms(str(tmp_path),'owner',request)

def web_fixture(tmp_path,monkeypatch,allow_output=True,swap_grant=False):
    work=tmp_path/'session-11111111-1111-4111-8111-111111111111/work'
    inputs=work/'inputs';inputs.mkdir(parents=True)
    media=b'owned synthetic media';(inputs/'clip.mp4').write_bytes(media)
    (work/'approved-inputs.json').write_text(json.dumps({'files':{'clip.mp4':hashlib.sha256(media).hexdigest()}}))
    grant=work/'video-output-grant.json'
    grant.write_text(json.dumps({'schema_version':1,'task_id':'a'*32,'allow_output':allow_output}))
    spec=importlib.util.spec_from_file_location('test_web_program_adapter',ROOT/'scenarios/remotion_edit/web_server.py')
    module=importlib.util.module_from_spec(spec);spec.loader.exec_module(module)
    state,calls,request=fake_runtime(tmp_path)
    programs=PublishedPrograms(str(tmp_path),'owner',request)
    monkeypatch.setattr(module,'from_environment',lambda:programs)
    original=importlib.util.spec_from_file_location
    def scene_spec(name,path,*args,**kwargs):
        result=original(name,path,*args,**kwargs)
        if name=='web_remotion_original':
            loader=result.loader.exec_module
            def load(scene):
                loader(scene)
                def render(version):
                    (work/'remotion/out/video.mp4').write_bytes(b'actual-render-stub')
                    if swap_grant:grant.write_text(json.dumps({'schema_version':1,'task_id':'b'*32,'allow_output':True}))
                    return {'source_version':version,'full_video_decode':True}
                scene.render_composition=render
            result.loader.exec_module=load
        return result
    monkeypatch.setattr(module.importlib.util,'spec_from_file_location',scene_spec)
    server=module.create_server(inputs)
    return work,server,programs,calls

def test_program_render_uses_existing_delivery_and_task_bound_audit(tmp_path,monkeypatch):
    work,server,programs,calls=web_fixture(tmp_path,monkeypatch)
    value=server._video_execute('source_test',{'title':'CURRENT'})
    assert value['program_id']=='source_test' and value['source_current'] is True
    assert value['policy_digest']=='policy-v1' and value['library_digest']=='library-v1'
    receipt=json.loads((work/'outputs/video'/('a'*32)/'delivery.json').read_text())
    assert receipt['task_id']=='a'*32 and receipt['full_video_decode'] is True
    for row in receipt['files']:
        assert hashlib.sha256((work/row['name']).read_bytes()).hexdigest()==row['sha256']
    records=[json.loads(x) for x in (work/'source-program-audit.jsonl').read_text().splitlines()]
    assert [r['kind'] for r in records]==['source_program_selected','source_program_rendered']
    assert all(r['task_id']=='a'*32 and r['policy_digest']=='policy-v1' for r in records)
    assert not (work/'session.jsonl').exists()

def test_program_render_requires_output_grant_before_materialization(tmp_path,monkeypatch):
    work,server,programs,calls=web_fixture(tmp_path,monkeypatch,allow_output=False)
    with pytest.raises(Exception,match='output permission'):server._video_execute('source_test',{})
    assert not any(row['operation']=='materialize' for row in calls)
    assert not (work/'source-program-audit.jsonl').exists()

def test_program_render_does_not_claim_success_after_task_changes(tmp_path,monkeypatch):
    work,server,programs,calls=web_fixture(tmp_path,monkeypatch,swap_grant=True)
    with pytest.raises(Exception,match='owning video task changed'):server._video_execute('source_test',{})
    records=[json.loads(x) for x in (work/'source-program-audit.jsonl').read_text().splitlines()]
    assert [r['kind'] for r in records]==['source_program_selected']
    assert not (work/'outputs/video'/('b'*32)).exists()
