"""Preview-only file ownership and heldout isolation; no Agent/API simulation."""
from argparse import Namespace
import hashlib
import json
import os
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

import pytest
from scenarios.agentic_vbench.trial import run

ROOT=Path(__file__).resolve().parents[1]


def preparation(tmp_path):
    official=tmp_path/'official'
    task=official/'tasks/agentic_vbench_assembly/agentic-vbench-assembly-task2/steps/solve'
    task.mkdir(parents=True)
    instruction=task/'instruction.md';instruction.write_text('Complete the current video task.')
    parent=tmp_path/'previous';parent.mkdir()
    effective={'role':'development','task_id':'agentic-vbench-assembly-task2','model':'gpt-6-luna',
               'task_sha256':hashlib.sha256(instruction.read_bytes()).hexdigest()}
    (parent/'effective.json').write_text(json.dumps(effective))
    (parent/'result.json').write_text('{"status":"completed","evaluation":{"reward":0}}')
    session=parent/'dsh/sessions/project/agentic-vbench-original';session.mkdir(parents=True)
    (session/'session.v3.jsonl.zstd').write_bytes(b'opaque original session bytes')
    (session/'session.lock').write_bytes(b'')
    for folder in ('workspace/inputs','workspace/code','workspace/outputs/code',
                   'media-workspace/materials','media-workspace/output','media-workspace/work'):
        (parent/folder).mkdir(parents=True)
    (parent/'workspace/code/edit.py').write_text('original model-authored program\n')
    (parent/'workspace/outputs/code/old-part.mp4').write_bytes(b'old intermediate media bytes')
    (parent/'media-workspace/output/solution.mp4').write_bytes(b'original video fixture, not a quality test')
    (parent/'verifier').mkdir();(parent/'verifier/reward.json').write_text('private verifier answer fixture')
    followup=tmp_path/'followup.txt';followup.write_text('Continue the same current task; configuration comes first.')
    args=Namespace(runtime=ROOT,official=official,output=tmp_path/'next',
        ledger_root=tmp_path/'unused-ledger',native_tools=ROOT/'src/adapters/research_native_tools.ts',
        env_file=None,roles=ROOT/'scenarios/agentic_vbench/roles.json',reference_program=None,
        store=None,owner='test',family='assembly',task=2,role='development',timeout=1,image='preview-only-image',
        call_model=False,model='gpt-6-luna',model_config=ROOT/'config/research-gpt-6-luna.json',
        request_recovery=True,continue_trial=parent,followup=followup)
    return parent,session,args


def preview(args):
    # Imports alone must not require an installed SDK or credentials in preview.
    modules={'src.adapters.harness.capability.capability_proposal':SimpleNamespace(
        CumulativeProposalGate=None,MODEL='deepseek-flash',MAX_TOKENS=393216),
        'src.adapters.harness.harness_runtime':SimpleNamespace(create_harness=None)}
    with patch.dict('sys.modules',modules),patch.dict(os.environ,{}):
        return run(args)


@pytest.mark.parametrize('status',['completed','failed'])
def test_continuation_preserves_previous_bytes_and_does_not_copy_verifier(tmp_path,status):
    parent,session,args=preparation(tmp_path)
    (parent/'result.json').write_text(json.dumps({'status':status,'evaluation':{'reward':0}}))
    before={p.relative_to(parent):p.read_bytes() for p in parent.rglob('*') if p.is_file()}
    result=preview(args)
    assert result['status']=='preview'
    assert result['effective']['continuation']['prior_session_id']==session.name
    assert result['effective']['dsh_home']==str(args.output/'dsh')
    assert result['effective']['continuation']['session_mode']=='fresh_original_SDK_session_with_existing_working_files'
    assert (args.output/'prior-session/session.v3.jsonl.zstd').read_bytes()==before[Path('dsh/sessions/project/agentic-vbench-original/session.v3.jsonl.zstd')]
    assert not (args.output/'prior-session/session.lock').exists()
    assert not (args.output/'verifier').exists()
    assert list((args.output/'workspace/outputs/code').iterdir())==[]
    assert (args.output/'media-workspace/work/previous-program-outputs'/parent.name/'old-part.mp4').read_bytes()==b'old intermediate media bytes'
    (args.output/'workspace/code/edit.py').write_text('new owned revision')
    assert {p.relative_to(parent):p.read_bytes() for p in parent.rglob('*') if p.is_file()}==before


@pytest.mark.parametrize('field,value',[('role','successor'),('model','deepseek-flash'),
    ('task_id','agentic-vbench-assembly-task13')])
def test_continuation_cannot_import_another_model_or_sealed_task(tmp_path,field,value):
    parent,session,args=preparation(tmp_path)
    previous=json.loads((parent/'effective.json').read_text());previous[field]=value
    (parent/'effective.json').write_text(json.dumps(previous))
    with pytest.raises(ValueError,match='same_finished_development_task_and_model'):
        preview(args)


def recovery_preparation(tmp_path):
    parent,session,args=preparation(tmp_path)
    args.role='successor';args.component_only=True;args.store=tmp_path/'empty-store';args.store.mkdir()
    args.goal_file=tmp_path/'goal.txt';args.goal_file.write_text('Deliver the explicit current edit and required output intervals.')
    args.instance_file=parent/'workspace/code/instance.json';args.instance_file.write_text('{"clips":[{"source":"1"}]}')
    roles={'study':'diagnostic','evaluation_role':'fixed_decision_execution_successor_paired',
           'evaluation_scope':'configured_full_clip_plan_v1','tasks':{'agentic-vbench-assembly-task2':'sealed_successor_paired'}}
    args.roles=tmp_path/'roles.json';args.roles.write_text(json.dumps(roles))
    source=parent/'source-snapshot';source.mkdir()
    (source/'component-goal.txt').write_bytes(args.goal_file.read_bytes())
    (source/'roles.json').write_bytes(args.roles.read_bytes())
    (source/'model-config.json').write_bytes(args.model_config.read_bytes())
    manifest=parent/'media-workspace/output/solution.json';manifest.write_text('{"segments":[{"start":0,"end":1}]}')
    prior=json.loads((parent/'effective.json').read_text())
    prior.update(role='successor',mode='baseline_empty_store',runtime=str(ROOT),image=args.image,
        timeout_seconds=900,evaluation_role=roles['evaluation_role'],evaluation_scope=roles['evaluation_scope'],
        native_tools_sha256=hashlib.sha256(args.native_tools.read_bytes()).hexdigest(),
        media_metadata_sha256='metadata-version')
    (parent/'effective.json').write_text(json.dumps(prior))
    previous={'status':'completed','elapsed_seconds':182}
    (parent/'result.json').write_text(json.dumps(previous));args.timeout=718
    checker=ROOT/'scenarios/agentic_vbench/component_quality.py'
    report={'passed':False,'scope':'configured_full_clip_manifest_v1','reason':"'output'",
        'evaluator_sha256':hashlib.sha256(checker.read_bytes()).hexdigest(),
        'inputs':{'manifest':{'sha256':hashlib.sha256(manifest.read_bytes()).hexdigest()},
                  'media_metadata':{'sha256':'metadata-version'}}}
    args.baseline_recovery_report=tmp_path/'failure.json';args.baseline_recovery_report.write_text(json.dumps(report))
    return parent,session,args,prior,previous,roles


def test_explicit_recovery_is_secondary_and_preserves_primary_files(tmp_path):
    parent,session,args,prior,previous,roles=recovery_preparation(tmp_path)
    before={p.relative_to(parent):p.read_bytes() for p in parent.rglob('*') if p.is_file()}
    result=preview(args)
    policy=result['effective']['continuation']['baseline_recovery']
    assert policy['remaining_seconds']==718 and policy['maximum_recovery_stages']==1
    assert policy['learning_eligible'] is False and policy['original_primary_result_preserved'] is True
    assert result['effective']['role']=='successor'
    assert not (args.output/'verifier').exists()
    assert {p.relative_to(parent):p.read_bytes() for p in parent.rglob('*') if p.is_file()}==before


@pytest.mark.parametrize('change',['reuse','other_scope','second_stage','more_time','changed_goal','passed','changed_manifest'])
def test_secondary_recovery_does_not_open_other_successors_or_reset_time(tmp_path,change):
    from scenarios.agentic_vbench.trial import baseline_recovery_policy
    parent,session,args,prior,previous,roles=recovery_preparation(tmp_path)
    if change=='reuse':prior['mode']='reuse'
    elif change=='other_scope':roles['evaluation_scope']='official_video_task'
    elif change=='second_stage':prior['continuation']={'parent':'already-recovered'}
    elif change=='more_time':args.timeout=719
    elif change=='changed_goal':args.goal_file.write_text('different task')
    elif change=='passed':
        report=json.loads(args.baseline_recovery_report.read_text());report['passed']=True
        args.baseline_recovery_report.write_text(json.dumps(report))
    elif change=='changed_manifest':(parent/'media-workspace/output/solution.json').write_text('{}')
    with pytest.raises(ValueError,match='same_failed_fixed_execution_baseline_one_recovery'):
        baseline_recovery_policy(args,prior,previous,roles,parent,ROOT)
