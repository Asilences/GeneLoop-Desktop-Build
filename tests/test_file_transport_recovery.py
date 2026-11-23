"""Free regressions for observed source text and durable observer-only repair."""
import pytest
from src.adapters.operation_runner import mcp_transport_interrupted,recovery_source_transition
from src.motif_core.reuse.experience_registry import durable,sha


def test_recovery_preserves_original_scene_composition_and_rejects_tampering(tmp_path):
    from src.adapters.operation_runner import frozen_scene_patch
    patch=tmp_path/'input.yml';patch.write_text('original extra plugin and provider')
    out=tmp_path/'run';out.mkdir()
    saved=frozen_scene_patch(out,{'patch':str(patch)})
    patch.write_text('different default patch')
    assert frozen_scene_patch(out,{},resume=True)==saved
    assert open(saved).read()=='original extra plugin and provider'
    from pathlib import Path
    Path(saved).write_text('changed')
    with pytest.raises(ValueError,match='composition changed'):frozen_scene_patch(out,{},resume=True)
    with pytest.raises(ValueError,match='explicit migration'):frozen_scene_patch(tmp_path,{},resume=True)

def event(text,error=False):
    return {'type':'tool/result','data':{'message':{'content':[{'type':'tool-result','isError':error,'content':[{'type':'text','text':text}]}]}}}

def test_document_prose_never_interrupts_successful_mcp_results():
    assert not mcp_transport_interrupted(event('sessions '+('public source data '*1000)+'closed'))
    assert not mcp_transport_interrupted(event('connection closed; broken pipe; end of stream'))
    assert mcp_transport_interrupted(event('MCP connection closed',True))
    assert not mcp_transport_interrupted(event('file not found',True))

def test_only_recorded_observer_repair_can_continue_original_task(tmp_path):
    origin=tmp_path/'origin';out=tmp_path/'out';job=tmp_path/'job.json'
    before={'src/adapters/operation_runner.py':'before','mcp.py':'unchanged'}
    after={**before,'src/adapters/operation_runner.py':'after'}
    durable(origin/'source-code.json',before)
    durable(origin/'enrollment.json',{'job_file':str(job)})
    file=out/'recovery-observer-transition.json'
    durable(file,{'format':'sss-observer-recovery-transition-v1','before':before,'after':after,'original_enrollment_sha256':sha(origin/'enrollment.json')})
    with pytest.raises(ValueError,match='lacks original durable'):recovery_source_transition(origin,out,after)
    durable(tmp_path/'job.json.events/1.json',{'kind':'host_authorized_observer_repair','detail':{'transition_sha256':sha(file)}})
    assert recovery_source_transition(origin,out,after)['sha256']==sha(file)
    with pytest.raises(ValueError,match='outside recorded observer repair'):recovery_source_transition(origin,out,{**after,'mcp.py':'changed'})
    assert recovery_source_transition(origin,out,before) is None
