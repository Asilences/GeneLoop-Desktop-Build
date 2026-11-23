"""The verifier CLI cannot silently reintroduce the removed experiment quota."""
import json,os,subprocess,sys,shutil
from pathlib import Path
from uuid import uuid4
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'scenarios/file-management'))
from management_prepare import prepare
from management_tools import ManagementScene
from common import sha


def test_fourth_cli_check_preserves_quality_and_round_archive(monkeypatch):
    home=ROOT/'.local/acceptance-round-tests'/uuid4().hex
    work=home/'management-copies/test';work.mkdir(parents=True)
    (work/'note.txt').write_text('Original bytes remain.')
    try:
        monkeypatch.setenv('HARLESS_MANAGEMENT_PRIVATE_ROOT',str(home))
        spec=prepare(home/'task',work,task_id='unlimited-verifier-diagnostic',objective='保持原件不变并提交报告',owner='fixture',workspace_id='fixture',delivery_contract={'format':'sss-file-delivery-v1','preserve_originals':True,'exact_tree':True})
        output=home/'delivery';scene=ManagementScene(spec,output);scene.read_task();receipt=scene.submit_report('Original note preserved; no changes.',None,[])
        task=home/'task/input.json';archive=home/'archive';env={k:v for k,v in os.environ.items() if k!='_'}
        args=[sys.executable,str(ROOT/'scripts/validate-file-delivery.py'),'--task-file',str(task),'--task-sha256',sha(task),'--delivery-root',str(output),'--archive-root',str(archive),'--round','3']
        result=subprocess.run(args,input=json.dumps({'receipt':receipt,'events':[]}),text=True,capture_output=True,env=env)
        data=json.loads(result.stdout)
        assert result.returncode==0 and data['passed'] is True and data['round']==3
        saved=archive/'round-03/result.json';original=saved.read_bytes()
        # A repeated check cannot overwrite earlier evidence, even when unlimited.
        repeat=subprocess.run(args,input='{}',text=True,capture_output=True,env=env)
        assert repeat.returncode!=0 and saved.read_bytes()==original
        assert (work/'note.txt').read_text()=='Original bytes remain.'
        # A later invalid delivery still fails the same quality gate, not the round number.
        (work/'unrequested.txt').write_text('unrequested')
        args[-1]='4';failed=subprocess.run(args,input=json.dumps({'receipt':receipt,'events':[]}),text=True,capture_output=True,env=env)
        value=json.loads(failed.stdout)
        assert failed.returncode==0 and value['passed'] is False
        assert 'acceptance round limit' not in json.dumps(value)
    finally:shutil.rmtree(home)
