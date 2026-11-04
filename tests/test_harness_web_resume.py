"""Independent Web resume guards; no server, model, or process is launched."""
import importlib.util
import json
import os
from pathlib import Path
from types import SimpleNamespace
import pytest

ROOT=Path(__file__).resolve().parents[1]
spec=importlib.util.spec_from_file_location('web_resume',ROOT/'scripts/harness-web.py')
web=importlib.util.module_from_spec(spec);spec.loader.exec_module(web)

def prepare(tmp_path):
    out=tmp_path/'run';out.mkdir()
    for name in ('work','dsh'):(out/name).mkdir()
    for name,value in [('policy.json',{'user_id':'owner','provider_mode':'real'}),
        ('process.json',{'launcher_pid':999999991,'harness_pid':999999992}),('effective-config.json',{})]:
        (out/name).write_text(json.dumps(value))
    (out/'events.jsonl').write_text('existing trace\n');(out/'ledger.jsonl').write_text('existing cost\n')
    (out/'access-url.txt').write_text('http://localhost/?token=diagnostic-only')
    args=SimpleNamespace(resume=True,run_id='a'*32,user_id='owner',real_model=True)
    return out,args

@pytest.mark.skipif(os.name=='nt',reason='Linux-only process proof')
def test_resume_preserves_home_output_trace_cost_and_private_history(tmp_path):
    out,args=prepare(tmp_path);startup=web.prepare_run_directory(args,out)
    assert startup.name.startswith('startup-resume-')
    assert (out/'ledger.jsonl').read_text()=='existing cost\n' and (out/'events.jsonl').read_text()=='existing trace\n'
    history=next((out/'resume-history').iterdir())
    assert (history/'policy.json').is_file() and (history/'access-url.txt').is_file()
    assert not (out/'access-url.txt').exists()

@pytest.mark.parametrize('issue',['live','other-owner','other-provider'])
def test_resume_rejects_live_or_changed_ownership_before_touching_credentials(tmp_path,issue):
    out,args=prepare(tmp_path)
    if issue=='live':(out/'process.json').write_text(json.dumps({'launcher_pid':os.getpid(),'harness_pid':999999992}))
    elif issue=='other-owner':args.user_id='other'
    else:args.real_model=False
    with pytest.raises(ValueError):web.prepare_run_directory(args,out)
    assert (out/'access-url.txt').is_file()

def test_shutdown_uses_budget_alias_and_preserves_unknown_external_counters(tmp_path):
    out,args=prepare(tmp_path);task=out/'task';task.mkdir();p=task/'task-state.json';p.write_text('{}')
    (task/'budget-route.json').write_text(json.dumps({'budget_session_id':'budget-native-alias'}))
    calls=[]
    class Registry:
        def stats(self,session):
            calls.append(session)
            if session!='budget-native-alias':raise KeyError('missing')
            return {'upstream_requests':5}
    assert web.shutdown_local_stats(Registry(),p,{'session_id':'native-session'})=={'upstream_requests':5}
    assert calls==['budget-native-alias']
    (task/'budget-route.json').write_text(json.dumps({'budget_session_id':'external-only'}))
    original={'session_id':'native-session','stats':{'upstream_requests':81}}
    assert web.shutdown_local_stats(Registry(),p,original) is None
    assert original['stats']['upstream_requests']==81


@pytest.mark.skipif(os.name!='nt',reason='Windows 8.3 path alias regression')
def test_preset_accepts_windows_short_root_alias(tmp_path):
    import ctypes
    root=tmp_path/'Long temporary output directory';root.mkdir()
    buffer=ctypes.create_unicode_buffer(32768)
    size=ctypes.windll.kernel32.GetShortPathNameW(str(root),buffer,len(buffer))
    assert size and size<len(buffer)
    alias=Path(buffer.value)
    if str(alias).lower()==str(root).lower():pytest.skip('8.3 aliases disabled on this volume')
    preset=web.prepare_preset_directory(SimpleNamespace(resume=False),alias)
    assert preset==root.resolve()/'presets/sss-task'


@pytest.mark.skipif(os.name=='nt',reason='Linux-only process proof')
def test_resume_reuses_preset_after_preserving_previous_config(tmp_path):
    out,args=prepare(tmp_path);preset=out/'presets/sss-task';preset.mkdir(parents=True)
    (preset/'agent.cordis.yml').write_text('old agent config')
    (preset/'preset.yml').write_text('old preset config')
    web.prepare_run_directory(args,out)
    assert web.prepare_preset_directory(args,out)==preset
    history=next((out/'resume-history').iterdir())
    assert (history/'preset-agent.cordis.yml').read_text()=='old agent config'
    assert (history/'preset-preset.yml').read_text()=='old preset config'
    args.resume=False
    with pytest.raises(FileExistsError):web.prepare_preset_directory(args,out)


@pytest.mark.skipif(os.name=='nt',reason='Linux link guards')
@pytest.mark.parametrize('issue',['directory-symlink','file-symlink','file-hardlink'])
def test_resume_rejects_redirected_preset_before_overwriting(tmp_path,issue):
    out,args=prepare(tmp_path);preset=out/'presets/sss-task'
    external=tmp_path/'external';external.mkdir();protected=external/'agent.cordis.yml';protected.write_text('protected')
    preset.parent.mkdir()
    if issue=='directory-symlink':preset.symlink_to(external,target_is_directory=True)
    else:
        preset.mkdir()
        if issue=='file-symlink':(preset/'agent.cordis.yml').symlink_to(protected)
        else:os.link(protected,preset/'agent.cordis.yml')
    with pytest.raises(ValueError):web.prepare_preset_directory(args,out)
    assert protected.read_text()=='protected'
