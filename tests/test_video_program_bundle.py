"""Deployment guards only; fixtures are never claimed as learned model results."""
import hashlib
import json
from pathlib import Path
import pytest
from src.adapters import harless_video_program_bundle as bundle

ROOT=Path(__file__).resolve().parents[1]

def fixture(tmp_path):
    store=tmp_path/'store';store.mkdir();name='round-'+'a'*24;directory=store/name;directory.mkdir()
    (store/'latest.json').write_text(json.dumps({'policy':name+'/policy.json','library':name+'/source-library.json'}))
    for name in ('policy.json','source-library.json','rsi-update.json','rsi-publication.json'):
        (directory/name).write_text('{}')
    return store,directory

def test_store_limits_files_to_published_runtime(tmp_path):
    store,directory=fixture(tmp_path)
    root,locks=bundle.fixed_store(str(store));assert root==store and len(locks)==5
    (store/'raw-private-events.jsonl').write_text('{}')
    with pytest.raises(ValueError,match='non-runtime'):bundle.fixed_store(str(store))

def test_store_requires_complete_receipts(tmp_path):
    store,directory=fixture(tmp_path);(directory/'rsi-publication.json').unlink()
    with pytest.raises(ValueError,match='receipt set'):bundle.fixed_store(str(store))

def test_store_rejects_redirected_file(tmp_path):
    store,directory=fixture(tmp_path);p=directory/'policy.json';p.unlink()
    outside=tmp_path/'outside';outside.write_text('{}')
    try:p.symlink_to(outside)
    except OSError:pytest.skip('symlinks unavailable')
    with pytest.raises(ValueError,match='redirected'):bundle.fixed_store(str(store))

def test_empty_configuration_keeps_baseline(tmp_path):
    scene={};bundle.configure_video_programs(ROOT,scene,None,None)
    assert scene['rsi_unavailable_reason']=='video_program_not_deployed'
    with pytest.raises(ValueError,match='requires'):bundle.configure_video_programs(ROOT,{},str(tmp_path),None)

def test_frozen_schemas_match_registered_native_surface():
    schemas=json.loads((ROOT/'scenarios/remotion_edit/web-tool-schemas.json').read_text())
    scenario=json.loads((ROOT/'scenarios/remotion_edit/web-scenario.json').read_text())
    assert len(schemas)==11
    assert [r['name'] for r in schemas]==scenario['allowed_tools']
    assert all(isinstance(r['parameters'],dict) and isinstance(r['description'],str) for r in schemas)

def test_original_runtime_rejection_does_not_become_fallback(monkeypatch,tmp_path):
    store,directory=fixture(tmp_path)
    def rejected(*args):raise ValueError('original publication rejected')
    monkeypatch.setattr(bundle,'PublishedPrograms',rejected)
    with pytest.raises(ValueError,match='original publication rejected'):
        bundle.load_video_program_bundle(ROOT,str(store),'study-owner')

def test_loader_records_byte_locks_and_original_policy(monkeypatch,tmp_path):
    store,directory=fixture(tmp_path)
    class Fake:
        def __init__(self,*args):
            self.policy={'digest':'a'*64,'library_digest':'b'*64,'form':{'agent_instruction':'same both arms'},'verdict':{'accepted':True}}
            self.library_path=str(directory/'source-library.json');self.naming='opaque';self.binding='full'
            self.catalog={'programs':[]}
        def check(self):pass
    class Tool:
        name='reuse_fixture';description='fixture tool';input_schema={'type':'object','properties':{}}
    monkeypatch.setattr(bundle,'PublishedPrograms',Fake)
    monkeypatch.setattr(bundle,'learned_tool_definitions',lambda *args:[Tool()])
    scene={'allowed_tools':['native'],'mcp_rows':[{'config':{'serverName':'remotion'}}],'config_sha256':'before'}
    bundle.configure_video_programs(ROOT,scene,str(store),'owner')
    assert scene['runtime_kind']=='video_program_v1' and len(scene['certified_tool_schemas'])==12
    assert scene['video_program_tools']==['mcp__remotion__reuse_fixture']
    assert [r['name'] for r in scene['certified_tool_schemas']]==sorted(r['name'] for r in scene['certified_tool_schemas'])
    assert scene['runtime_library_sha256']==hashlib.sha256(b'{}').hexdigest()
    assert len(scene['video_program_file_locks'])==5
    assert scene['mcp_rows'][0]['config']['env']['GENELOOP_VIDEO_MOTIF_STORE']==str(store)
    assert scene['video_program_agent_instruction']=='same both arms'


def test_video_runtime_locks_own_code_and_original_protocol():
    locks=bundle.runtime_code_locks(ROOT)
    assert len(locks)==len(bundle.VIDEO_RUNTIME_CODE)
    for name in ('src/adapters/harless_video_program_bundle.py','src/adapters/source_program_runtime.ts','schemas/rsi-protocol-v1.schema.json'):
        assert locks[str(ROOT/name)]==hashlib.sha256((ROOT/name).read_bytes()).hexdigest()
