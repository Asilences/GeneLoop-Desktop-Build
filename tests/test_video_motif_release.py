import hashlib,importlib.util,json,sys
from pathlib import Path
import pytest
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'scripts'))
spec=importlib.util.spec_from_file_location('video_release_service',ROOT/'scripts/geneloop_service.py')
service=importlib.util.module_from_spec(spec);spec.loader.exec_module(service)
def fixture(tmp_path):
 root=tmp_path/'code';(root/'config').mkdir(parents=True)
 (root/'scene.md').write_text('Video')
 (root/'config/geneloop-capabilities.md').write_text('Common')
 registry={'scenes':[{'id':'video-editing','instructions':'scene.md','adapter':'video'}]}
 data=json.dumps(registry).encode();(root/'config/harless-scenes.json').write_bytes(data)
 store=tmp_path/'published';store.mkdir();file=store/'latest.json';file.write_text('{}')
 scene={'id':'video-editing','instructions':'Video\n\nCommon','instructions_sha256':hashlib.sha256(b'Video\n\nCommon').hexdigest(),
 'runtime_kind':'video_program_v1','video_program_store':str(store),'video_program_owner':'test-owner','video_program_policy_digest':'a'*64,
 'video_program_file_locks':{str(file):hashlib.sha256(file.read_bytes()).hexdigest()}}
 policy={'scenes':[scene],'scene_registry_sha256':hashlib.sha256(data).hexdigest()}
 owner=tmp_path/'owner.json';gateway=tmp_path/'gateway.json';service.save(owner,policy)
 service.save(gateway,{'memberSceneDeployment':{'projectRoot':str(root),'videoMotifStore':str(store),'videoMotifOwner':'test-owner'},'memberPolicy':policy})
 return {'gateway_config':str(gateway),'owner':{'env':{'SSS_WEB_POLICY':str(owner)}}},file,gateway

def test_published_video_snapshot_rejects_runtime_mutation_before_restart(tmp_path):
 plan,file,_=fixture(tmp_path);service.assert_scene_snapshot(plan);file.write_text('{"changed":true}')
 with pytest.raises(RuntimeError,match='video Motif file changed'):service.assert_scene_snapshot(plan)

def test_video_snapshot_rejects_unavailable_or_wrong_owner(tmp_path):
 plan,_,gateway=fixture(tmp_path);g=json.loads(gateway.read_text());g['memberPolicy']['scenes'][0]['video_program_owner']='other-owner';service.save(gateway,g)
 with pytest.raises(RuntimeError,match='unavailable or stale'):service.assert_scene_snapshot(plan)
