"""Product compatibility diagnostics; no model calls or Docker startup."""
import atexit
import hashlib
import importlib.util
import json
from pathlib import Path
from types import SimpleNamespace
import pytest
from src.adapters.harless_rsi_bundle import load_product_bundle

ROOT=Path(__file__).resolve().parents[1]
IMMUTABLE=('library.json','online-manifest.json','task.json','tool-schemas.json','source-evidence.json')


def read(path):return json.loads(path.read_text(encoding='utf-8'))
def sha(path):return hashlib.sha256(path.read_bytes()).hexdigest()


@pytest.mark.parametrize('old_name,new_name,scene',[
    ('paper-web-v40','paper-web-v41','paper-proofreading'),
    ('ppt-master-v37','ppt-master-v38','ppt'),
])
def test_container_compatibility_retains_original_program_and_report(old_name,new_name,scene):
    old,new=(ROOT/'motif-libraries'/name for name in (old_name,new_name))
    for name in IMMUTABLE:assert (old/name).read_bytes()==(new/name).read_bytes(),name
    before,after=read(old/'learning-report.json'),read(new/'learning-report.json')
    record=after.pop('capability_container_compatibility')
    assert after==before
    assert record['previous_certification_sha256']==sha(old/'certification.json')
    assert record['changed_code_locks']==['scenarios/remotion_edit/server.py']
    assert record['additional_code_locks']==['scripts/reexport-capability-container-compat.py']
    assert record['new_training_tasks']==record['model_requests']==0
    assert record['raw_traces_replayed'] is record['quality_cost_promoted'] is record['capability_runtime_certified'] is False
    old_locks=read(old/'certification.json')['code_locks'];new_locks=read(new/'certification.json')['code_locks']
    assert {name for name,value in old_locks.items() if new_locks[name]!=value}=={'scenarios/remotion_edit/server.py'}
    assert set(new_locks)-set(old_locks)=={'scripts/reexport-capability-container-compat.py'}
    for name,value in read(old/'entry.json')['files'].items():assert sha(old/name)==value
    selected=next(row['rsi']['runtime_bundle'] for row in read(ROOT/'config/harless-scenes.json')['scenes'] if row['id']==scene)
    if selected=='motif-libraries/'+new_name:
        admitted=load_product_bundle(ROOT,new,scene)
        assert admitted['runtime_mode']=='execute' and admitted['quality_cost_promoted'] is False


@pytest.mark.parametrize('with_media_tools',[False,True])
def test_optional_nonce_changes_only_ownership_fields_of_existing_launcher(tmp_path,monkeypatch,with_media_tools):
    work=tmp_path/'work';work.mkdir()
    monkeypatch.setenv('REMOTION_WORK',str(work));monkeypatch.setenv('REMOTION_RUNTIME',str(tmp_path));monkeypatch.setenv('REMOTION_IMAGE','diagnostic-no-docker')
    if with_media_tools:monkeypatch.setenv('REMOTION_MEDIA_TOOLS',str(tmp_path/'tools'))
    else:monkeypatch.delenv('REMOTION_MEDIA_TOOLS',raising=False)
    monkeypatch.setattr(atexit,'register',lambda *args:None)
    nonce='a'*32
    def launch(scoped):
        if scoped:
            monkeypatch.setenv('REMOTION_CONTAINER_NAME','geneloop-cap-'+nonce);monkeypatch.setenv('REMOTION_CONTAINER_NONCE',nonce)
        else:
            monkeypatch.delenv('REMOTION_CONTAINER_NAME',raising=False);monkeypatch.delenv('REMOTION_CONTAINER_NONCE',raising=False)
        spec=importlib.util.spec_from_file_location('container_compat_scene_'+str(scoped),ROOT/'scenarios/remotion_edit/server.py')
        module=importlib.util.module_from_spec(spec);spec.loader.exec_module(module)
        captured=[]
        monkeypatch.setattr(module.subprocess,'check_output',lambda args,**kwargs:captured.append(list(args)) or 'diagnostic-id')
        monkeypatch.setattr(module.subprocess,'run',lambda *args,**kwargs:SimpleNamespace(returncode=0,stdout='',stderr=''))
        module.run_command('true');return captured[0]
    legacy,scoped=launch(False),launch(True)
    assert scoped[2:6]==['--name','geneloop-cap-'+nonce,'--label','geneloop.capability_nonce='+nonce]
    restored=scoped[:2]+scoped[6:]
    restored[restored.index('geneloop.experiment=source-capability-v1')]='geneloop.experiment=remotion-motivation-20261027-v1'
    restored[restored.index('geneloop.task='+nonce)]='geneloop.task='+work.name
    assert restored==legacy
