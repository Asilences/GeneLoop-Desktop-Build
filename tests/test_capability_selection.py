"""Real Python->TS Store selection; runtime/checker dispatch uses diagnostic stubs."""
import importlib.util
import json
import tempfile
from pathlib import Path
import pytest
from src.adapters.capability_feedback import CapabilityFeedback
from src.adapters.capability_contract import capability_digest
from tests.test_capability_feedback import fixture, fact
from tests.test_capability_improvement import put

ROOT=Path(__file__).resolve().parents[1]
spec=importlib.util.spec_from_file_location('selector',ROOT/'scripts/select-capability-execution.py')
selector=importlib.util.module_from_spec(spec);spec.loader.exec_module(selector)


@pytest.mark.parametrize('quality_passed',[True,False])
def test_feedback_selection_is_dispatched_and_quality_returns_to_selection(tmp_path,monkeypatch,quality_passed):
    manager,library,evidence,_=fixture(tmp_path);a,b=library['snapshot']['roots']
    fact(manager,a,evidence,cost=3);fact(manager,b,evidence,cost=1)
    put(tmp_path/'seed.json',library['snapshot']);put(tmp_path/'args.json',{'value':5})
    put(tmp_path/'manifest.json',{'owner':'owner','task_id':'diagnostic','grant':{'revoked':False}})
    put(tmp_path/'specification.json',{'diagnostic':True})
    (ROOT/'.local').mkdir(exist_ok=True)
    with tempfile.TemporaryDirectory(dir=ROOT/'.local') as private:
        plan={'owner':'owner','seed':str(tmp_path/'seed.json'),'store':str(tmp_path/'store'),
            'feedback_directory':str(tmp_path/'feedback'),'eligible':[a,b],'scope':'same-task-rubric',
            'manifest':str(tmp_path/'manifest.json'),'args':str(tmp_path/'args.json'),
            'specification':str(tmp_path/'specification.json'),'output':str(Path(private)/'run')}
        output,result=selector.select(plan)  # actual existing TS Store export, no model
        assert result['root']==b
        manifest=json.loads((output/'manifest.json').read_text(encoding='utf-8'))
        assert manifest['grant']['root']==b
        assert manifest['grant']['arguments_sha256']==capability_digest({'value':5})
        calls=[]
        def diagnostic_child(command,**kwargs):
            calls.append(command)
            if '--root' in command:
                assert json.loads(Path(command[command.index('--root')+1]).read_text(encoding='utf-8'))==b
                kwargs['stdout'].write(json.dumps({'status':'succeeded','root':b}))
            else:
                kwargs['stdout'].write(json.dumps({'passed':quality_passed,'checks':[{'status':'passed' if quality_passed else 'failed'}]}))
            return 0
        monkeypatch.setattr(selector,'run_child',diagnostic_child)
        assert selector.execute(plan,output,result)==(0 if quality_passed else 2)
        assert len(calls)==2
        # Missing observed cost stays unknown; failures actually demote b.
        state=manager.read()
        latest=[f for f in state['facts'].values() if f['cost'] is None]
        assert len(latest)==1 and latest[0]['status']==('passed' if quality_passed else 'failed')
        assert manager.select_execution(library,[a,b],'same-task-rubric')[0]==a
