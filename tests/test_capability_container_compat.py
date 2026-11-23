"""Product compatibility diagnostics; no model calls or Docker startup."""
import atexit
import importlib.util
import os
from pathlib import Path
from types import SimpleNamespace
import pytest

ROOT=Path(__file__).resolve().parents[1]


@pytest.mark.parametrize('with_media_tools',[False,True])
def test_optional_nonce_changes_only_ownership_fields_of_existing_launcher(tmp_path,monkeypatch,with_media_tools):
    work=tmp_path/'work';work.mkdir()
    monkeypatch.setenv('REMOTION_WORK',str(work));monkeypatch.setenv('REMOTION_RUNTIME',str(tmp_path));monkeypatch.setenv('REMOTION_IMAGE','diagnostic-no-docker')
    if with_media_tools:monkeypatch.setenv('REMOTION_MEDIA_TOOLS',str(tmp_path/'tools'))
    else:monkeypatch.delenv('REMOTION_MEDIA_TOOLS',raising=False)
    monkeypatch.setattr(atexit,'register',lambda *args:None)
    # Command assembly is diagnostic on Windows too; Docker execution is Linux.
    monkeypatch.setattr(os,'getuid',lambda:1234,raising=False)
    monkeypatch.setattr(os,'getgid',lambda:1234,raising=False)
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
