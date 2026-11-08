"""Public SDK observer composition must preserve task and shutdown behavior."""
from types import SimpleNamespace

import pytest

from src.adapters import harness_runtime, geneloop_learning_trace


@pytest.mark.parametrize('observer_fails',[False,True])
def test_sdk_closes_before_privacy_and_preserves_original_observer(monkeypatch,tmp_path,observer_fails):
    import deepseek_harness
    order,received=[],[]
    notification=SimpleNamespace(method='session.event',payload={'sessionId':'owned',
        'event':{'type':'user/message','data':{'content':[{'type':'text','text':'owner@example.com'}]}}})
    expected=SimpleNamespace(session_id='owned',finish_reason='completed')
    class Harness:
        def __init__(self,**kwargs):pass
        def run(self,input,*,session_id,on_notification):
            order.append('run');on_notification(notification);return expected
        def close(self):order.append('closed');return 'original-close'
    monkeypatch.setattr(deepseek_harness,'DeepSeekHarness',Harness)
    monkeypatch.setattr(harness_runtime,'launch_args',lambda root,patches:('node','diagnostic'))
    def capture(output,events,**kwargs):
        assert order[-1]=='closed'
        assert events==[notification.payload['event']]
        assert kwargs['status']==('failed' if observer_fails else 'completed')
        order.append('privacy')
        raise RuntimeError('/private/account synthetic-error')
    monkeypatch.setattr(geneloop_learning_trace,'capture_native_events',capture)
    harness=harness_runtime.create_harness(root=tmp_path,patches=())
    def observe(value):
        received.append(value)
        if observer_fails:raise RuntimeError('original-task-observer')
    if observer_fails:
        with pytest.raises(RuntimeError,match='^original-task-observer$'):
            harness.run('task',session_id='owned',on_notification=observe)
    else:
        assert harness.run('task',session_id='owned',on_notification=observe) is expected
    assert received==[notification] and received[0] is notification
    assert order==['run']
    assert harness.close()=='original-close'
    assert harness.wait_for_privacy(timeout=2)
    assert order==['run','closed','privacy']
    assert harness.close()=='original-close'
    assert order==['run','closed','privacy','closed']


def test_sdk_shutdown_returns_while_privacy_is_blocked_and_can_be_waited(monkeypatch,tmp_path):
    import deepseek_harness
    import threading
    started,released=threading.Event(),threading.Event()
    class Harness:
        def __init__(self,**kwargs):pass
        def run(self,input,*,session_id,on_notification):
            on_notification(SimpleNamespace(method='session.event',payload={'sessionId':session_id,
                'event':{'type':'user/message','data':{'content':[]}}}))
            return SimpleNamespace(session_id=session_id,finish_reason='completed')
        def close(self):return 'closed'
    monkeypatch.setattr(deepseek_harness,'DeepSeekHarness',Harness)
    monkeypatch.setattr(harness_runtime,'launch_args',lambda *args:('node','diagnostic'))
    def capture(*args,**kwargs):
        started.set()
        assert released.wait(timeout=3)
    monkeypatch.setattr(geneloop_learning_trace,'capture_native_events',capture)
    harness=harness_runtime.create_harness(root=tmp_path,patches=())
    try:
        harness.run('task',session_id='owned')
        assert harness.close()=='closed'
        assert started.wait(timeout=1) and not released.is_set()
        assert harness.wait_for_privacy(timeout=0.01) is False
    finally:
        released.set()
        assert harness.wait_for_privacy(timeout=2)
    assert len(harness.privacy_views)==1
