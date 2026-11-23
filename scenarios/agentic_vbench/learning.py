"""Thin scene projection into the original execution learner and certification.

No program synthesis, replacement miner, or scenario-specific Motif is defined
here. Whole-task and independently checked component qualification stay separate.
"""
from __future__ import annotations
import argparse
import hashlib
import json
import os
from pathlib import Path
import re
import sys
import shutil
import time


def _load(path):
    return json.loads(Path(path).read_text())


def project_program_operand(command, boundary):
    """Map a witnessed container source path into the original /work namespace.

    Only the plain Python source operand changes. Shell syntax, argv, program
    bytes and actual invocation evidence stay intact; the native parser still
    decides whether the resulting command is an admissible standalone call.
    """
    match=re.match(r'(\s*python(?:3(?:\.\d+)?)?\s+)(/[A-Za-z0-9_./-]+\.py)(?=\s|$)',command)
    workdir=boundary.get('workdir','').rstrip('/')
    if not match or not workdir or not match[2].startswith(workdir+'/'):
        return command,None
    relative=match[2][len(workdir)+1:]
    if '..' in Path(relative).parts:
        return command,None
    source=boundary['before']['files'].get('code/'+relative)
    expected=Path(boundary['workspace'])/'code'/relative
    if (not source or Path(source['path'])!=expected or not expected.is_file()
            or expected.is_symlink() or sha_file(expected)!=source['sha256']):
        return command,None
    projected=command[:match.start(2)]+'/work/'+relative+command[match.end(2):]
    return projected,{'kind':'witnessed_container_program_path_to_native_work',
        'original_command':command,'projected_command':projected,'source':source,
        'original_command_sha256':hashlib.sha256(command.encode()).hexdigest()}


def execution_boundary(reference, destination, verify):
    """Rebase recorded bytes into the original execution layout, never edit history."""
    boundary=json.loads(verify(reference))
    phase='before' if 'before' in boundary else 'after'
    if boundary[phase]['complete'] is not True:
        return boundary
    root=Path(boundary['workspace']).resolve()
    destination=Path(destination);destination.mkdir(parents=True,exist_ok=False)
    for name in ('inputs','code','outputs/code','command-tmp'):
        (destination/name).mkdir(parents=True,exist_ok=True)
    expected=set(boundary[phase]['files'])
    actual={p.relative_to(root).as_posix() for p in root.rglob('*') if p.is_file()}
    if actual!=expected or any(p.is_symlink() for p in root.rglob('*')):
        raise ValueError('recorded_boundary_file_set_changed')
    # Empty directories affect native freshness checks too. Do not erase a
    # model-created output directory when rebuilding a historical layout.
    for directory in root.rglob('*'):
        if directory.is_dir():
            (destination/directory.relative_to(root)).mkdir(parents=True,exist_ok=True)
    files={}
    for relative,source in boundary[phase]['files'].items():
        path=Path(relative)
        if path.is_absolute() or '..' in path.parts or Path(source['path']).resolve()!=root/path:
            raise ValueError('recorded_boundary_path_changed')
        raw=verify(source)
        target=destination/path;target.parent.mkdir(parents=True,exist_ok=True)
        shutil.copy2(source['path'],target)
        if target.read_bytes()!=raw:
            raise ValueError('execution_layout_copy_changed')
        files[relative]={**source,'path':str(target.resolve())}
    value={**boundary,'workspace':str(destination.resolve()),phase:{**boundary[phase],'files':files},
            'original_boundary':reference,'execution_layout_projection':{
                'scope':'identical_recorded_files_and_directories_with_empty_command_tmp',
                'file_count':len(files),'source_workspace':str(root)}}
    (destination.parent/(destination.name+'-layout.json')).write_text(json.dumps(value,indent=2))
    return value


def extract(runtime, trial, output):
    sys.path.insert(0, str(Path(runtime).resolve()))
    from src.rsi.feedback.capability_feedback import file_ref, verify
    from src.adapters.execution_learning_bridge import collect_shell_call
    trial, output = Path(trial), Path(output)
    effective, result = _load(trial/'effective.json'), _load(trial/'result.json')
    if effective['role'] == 'successor':
        raise ValueError('sealed_successor_cannot_enter_learning')
    output.mkdir(parents=True, exist_ok=False)
    shutil.copyfile(__file__,output/'learning-adapter.py')
    if not (trial/'events.jsonl').is_file() or not (trial/'native-tools.jsonl').is_file():
        summary={'task_id':effective['task_id'],'role':effective['role'],'learning_eligible':False,
            'script_candidates':0,'artifact_candidates':0,'source':[], 'boundary_evidence':[],
            'rejected':[{'reason':'original_execution_evidence_missing'}]}
        for name,value in (('script.json',[]),('artifact.json',[]),('summary.json',summary)):
            (output/name).write_text(json.dumps(value,indent=2)+'\n')
        return summary
    events = (trial/'events.jsonl').read_bytes()
    calls = {row['data']['callId']:row['data'] for row in map(json.loads,events.splitlines())
             if row.get('type') == 'tool/call'}
    goal = (trial/'prompt.txt').read_text()
    script, artifact, rejected, evidence, projections = [], [], [], [], []
    for row in map(json.loads,(trial/'native-tools.jsonl').read_text().splitlines()):
        if row['phase'] != 'finished' or row['name'] != 'execute':
            continue
        event = calls.get(row['call_id'], {})
        arguments = event.get('arguments')
        if isinstance(arguments, str):
            arguments = json.loads(arguments)
        if event.get('name') != 'execute' or arguments != row['arguments']:
            raise ValueError('native_command_event_mismatch')
        before=execution_boundary(row['boundary'],output/'execution-layout'/row['sequence']/'before',verify)
        after=execution_boundary(row['after_boundary'],output/'execution-layout'/row['sequence']/'after',verify)
        if before['before']['complete'] is not True or after['after']['complete'] is not True:
            rejected.append({'call_id':row['call_id'],'reason':'incomplete_execution_boundary'})
            continue
        command,projection=project_program_operand(row['arguments']['command'],before)
        if projection:
            projection_path=output/('command-projection-'+row['sequence']+'.json')
            projection_path.write_text(json.dumps({**projection,'call_id':row['call_id'],
                'native_event':file_ref(trial/'events.jsonl'),'native_tools':file_ref(trial/'native-tools.jsonl')},indent=2)+'\n')
            reference=file_ref(projection_path);evidence.append(reference);projections.append(reference)
        converted = collect_shell_call(task_id=effective['task_id'],call_id=row['call_id'],goal=goal,
            command=command,description=goal,stdout=row['result']['stdout'],
            workspace=before['workspace'],boundary=before,workdir=before['workdir'],after_boundary=after,
            events_sha256=hashlib.sha256(events).hexdigest(),succeeded=row['result']['returncode']==0)
        base = {'task_id':effective['task_id'],'scene':'agentic-vbench','workspace':before['workspace'],
                'approved_inputs':{},'events':file_ref(trial/'events.jsonl')}
        for destination, key in ((script,'candidates'),(artifact,'artifact_candidates')):
            if converted.get(key):
                destination.append({**base,'candidates':converted[key]})
        rejected.extend({'call_id':row['call_id'],**x} for x in converted['rejected'])
        layouts=output/'execution-layout'/row['sequence']
        evidence.extend([row['boundary'],row['after_boundary'],
            file_ref(layouts/'before-layout.json'),file_ref(layouts/'after-layout.json')])
    evaluation = result.get('evaluation', {})
    verifier = trial/'verifier/reward.json'
    reward=evaluation.get('reward')
    # Same task-admission rule as SkillsBenchTrial.evaluate/BenchmarkHost, not a
    # new requirement that every semantic slot must already be perfect. Native
    # source equivalence and successor task quality remain separate judgments.
    quality = (result['status']=='completed' and type(reward) in (int,float) and 0<reward<=1
               and {'solution.mp4','solution.json'}<=set(result.get('output_files',{}))
               and verifier.is_file() and hashlib.sha256(verifier.read_bytes()).hexdigest()==evaluation.get('evidence_sha256'))
    # A component-only trial has its own frozen task goal and independent checks.
    # This never upgrades a failed official video task or its old observations.
    local=result.get('component_evaluation',{})
    local_record=trial/'component-evaluation.json'
    component_programs=[]
    if (effective.get('evaluation_scope')=='configured_full_clip_manifest_v1'
            and result['status']=='completed' and local.get('passed') is True
            and local_record.is_file() and sha_file(local_record)==local.get('record_sha256')):
        import importlib.util
        spec=importlib.util.spec_from_file_location('component_quality_recheck',Path(__file__).parent/'component_quality.py')
        evaluator=importlib.util.module_from_spec(spec);spec.loader.exec_module(evaluator)
        refs=local['inputs']
        for ref in refs.values():verify(ref)
        rechecked=evaluator.evaluate(refs['configuration']['path'],refs['manifest']['path'],refs['media_metadata']['path'])
        if rechecked.get('passed') is True and local.get('evaluator_sha256')==sha_file(trial/'source-snapshot/component_quality.py')==sha_file(Path(__file__).parent/'component_quality.py'):
            frozen_program=_load(trial/'source-snapshot/roles.json').get('frozen_program_sha256')
            for row in artifact:
                for candidate in row['candidates']:
                    witness=candidate['witness']
                    produced=Path(witness['original_output'])/'solution.json'
                    if (candidate.get('source_sha256')==frozen_program
                            and refs['configuration']['sha256'] in witness.get('input_sha256',{}).values()
                            and produced.is_file() and sha_file(produced)==refs['manifest']['sha256']):
                        component_programs.append(candidate['id'])
    summary = {'task_id':effective['task_id'],'role':effective['role'],'learning_eligible':quality,
        'source_task_reward':reward,'source_admission':'original_BenchmarkHost_completed_and_reward_gt_zero',
        'source_quality_scope':'partial reward is not full task success; native certification and final paired quality are separate',
        'script_candidates':sum(len(x['candidates']) for x in script),
        'artifact_candidates':sum(len(x['candidates']) for x in artifact),
        'component_learning_eligible':bool(component_programs),
        'component_programs':component_programs,'component_scope':local.get('scope'),
        'source':[file_ref(trial/'result.json'),file_ref(trial/'effective.json'),file_ref(trial/'events.jsonl'),
                  file_ref(trial/'native-tools.jsonl'),file_ref(output/'learning-adapter.py'),
                  *([file_ref(local_record),file_ref(trial/'source-snapshot/component_quality.py')] if local_record.exists() else []),
                  *([file_ref(verifier)] if verifier.exists() else [])],
        'boundary_evidence':evidence,'command_projections':projections,'rejected':rejected,
        'scope':'original_extraction_not_certification_or_efficiency_evidence'}
    for name, value in (('script.json',script),('artifact.json',artifact),('summary.json',summary)):
        (output/name).write_text(json.dumps(value,ensure_ascii=False,indent=2)+'\n')
    return summary


def sha_file(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def qualify_plan(runtime, source, report, output):
    """Attach independently checked plan evidence without changing raw trials."""
    sys.path.insert(0, str(Path(runtime).resolve()))
    from src.rsi.feedback.capability_feedback import file_ref, verify
    try:
        from .plan_quality import evaluate, SCOPE
    except ImportError:
        from plan_quality import evaluate, SCOPE
    source, report, output = map(Path, (source, report, output))
    summary, proof = _load(source/'summary.json'), _load(report)
    if (summary['role'] not in ('development', 'certification') or proof.get('passed') is not True
            or proof.get('scope') != SCOPE or proof['task_id'] != summary['task_id']
            or proof['role'] != summary['role']
            or proof.get('evaluator_sha256') != sha_file(Path(__file__).with_name('plan_evaluation.py'))
            or proof.get('plan_evaluator_sha256') != sha_file(Path(__file__).with_name('plan_quality.py'))
            or proof['extraction'] != file_ref(source/'artifact.json')):
        raise ValueError('independent_normal_plan_qualification_required')
    refs = [*proof['source'], proof['extraction'], *proof['plan_inputs'].values(),
            proof['frame_evidence'], proof['generic_worker'], proof['generic_checker_source'],
            *proof['delivered'].values(), *proof['boundary_evidence'],
            *([proof['frozen_frame_worker']] if proof.get('frozen_frame_worker') else []),
            *summary['source'], *summary['boundary_evidence']]
    for reference in refs:
        verify(reference)
    plan = proof['plan_inputs']
    rechecked = evaluate(*(plan[key]['path'] for key in ('configuration','manifest','media_records','concat')))
    frames = json.loads(verify(proof['frame_evidence']))
    if (rechecked.get('passed') is not True or frames != proof['frame_quality']
            or frames.get('passed') is not True
            or proof['delivered']['solution.json']['sha256'] != plan['manifest']['sha256']):
        raise ValueError('plan_or_actual_delivery_quality_changed')
    candidates = [candidate for row in _load(source/'artifact.json') for candidate in row['candidates']
                  if candidate['id'] == proof['program_id']]
    if (len(candidates) != 1 or candidates[0]['source_sha256'] != proof['source_sha256']
            or candidates[0]['witness'].get('source_task_mode') != 'normal_execution'
            or candidates[0]['witness']['call_id'] != proof['producer_call_id']
            or candidates[0]['witness']['input_sha256'] != proof['input_sha256']):
        raise ValueError('actual_program_witness_changed')
    output.mkdir(parents=True, exist_ok=False)
    for name in ('script.json','artifact.json'):
        shutil.copyfile(source/name, output/name)
    shutil.copyfile(report, output/'plan-qualification.json')
    for name in ('plan_quality.py','plan_evaluation.py','learning.py'):
        shutil.copyfile(Path(__file__).with_name(name), output/name)
    qualified = {**summary, 'component_learning_eligible': True,
                 'component_programs': [proof['program_id']], 'component_scope': SCOPE,
                 'source': [*summary['source'], file_ref(output/'plan-qualification.json'), *refs,
                            *[file_ref(output/name) for name in ('plan_quality.py','plan_evaluation.py','learning.py')]],
                 'raw_extraction': file_ref(source/'summary.json'),
                 'scope': 'independent_configured_project_qualification_not_official_task_success_or_efficiency'}
    (output/'summary.json').write_text(json.dumps(qualified, indent=2)+'\n')
    return qualified


def certify(runtime, source, validation, store, output, owner, admission='task'):
    sys.path.insert(0, str(Path(runtime).resolve()))
    from src.adapters.execution_learning_pipeline import advance_execution_learning
    from benchmarks.evolution.benchmark_script_materials import BenchmarkScriptMaterials
    from src.rsi.feedback.capability_feedback import file_ref
    source, validation, output = Path(source), Path(validation), Path(output)
    a, b = _load(source/'summary.json'), _load(validation/'summary.json')
    qualified='component_learning_eligible' if admission=='component' else 'learning_eligible'
    if (not a.get(qualified) or not b.get(qualified) or a['task_id']==b['task_id']
            or b['role']!='certification' or a['role']=='successor'):
        raise ValueError('qualified_distinct_source_and_certification_tasks_required')
    if admission=='component' and a.get('component_scope')!=b.get('component_scope'):
        raise ValueError('same_independent_component_scope_required')
    output.mkdir(parents=True, exist_ok=False)
    materials = BenchmarkScriptMaterials(owner,store)
    outcomes, admitted_programs = [], set()
    for backend, filename in (('script_motif','script.json'),('artifact_motif','artifact.json')):
        if admission=='component' and backend!='artifact_motif':continue
        for i, origin in enumerate(_load(source/filename)):
            origin={**origin,'candidates':[c for c in origin['candidates'] if (backend,c['id']) not in admitted_programs]}
            if admission=='component':origin['candidates']=[c for c in origin['candidates'] if c['id'] in a['component_programs']]
            if not origin['candidates']:
                continue
            for j, held in enumerate(_load(validation/filename)):
                if admission=='component':
                    held={**held,'candidates':[c for c in held['candidates'] if c['id'] in b['component_programs']]}
                    if not held['candidates']:continue
                directory=output/(backend+'-'+str(i)+'-'+str(j));directory.mkdir()
                for name, row in (('source.json',origin),('validation.json',held)):
                    (directory/name).write_text(json.dumps(row,ensure_ascii=False,indent=2))
                try:
                    value=advance_execution_learning(file_ref(directory/'source.json'),materials.materials,
                        directory/'native-admission',validation=file_ref(directory/'validation.json'),backend=backend,
                        evidence=[*a['source'],*b['source'],*a['boundary_evidence'],*b['boundary_evidence']])
                except Exception as error:
                    value={'status':'failed','error':type(error).__name__+':'+str(error)}
                outcomes.append({'backend':backend,'source_row':i,'validation_row':j,'outcome':value})
                if value.get('status')=='registered':
                    from src.rsi.feedback.capability_feedback import verify
                    for program in json.loads(verify(value['library'])).get('programs',[]):
                        admitted_programs.add((backend,program['id']))
                    break
    catalog=materials.catalog()
    result={'outcomes':outcomes,'catalog':catalog,'model_requests':0,'admission_scope':admission,
            'scope':'original_compilation_native_certification_and_material_registration; successor_quality_unmeasured'}
    (output/'result.json').write_text(json.dumps(result,ensure_ascii=False,indent=2)+'\n')
    return result


def parameterize(args):
    """Project qualified component evidence into the original declaration learner."""
    source,trial=args.source.resolve(),args.trial.resolve()
    summary,effective,result=(_load(p) for p in (source/'summary.json',trial/'effective.json',trial/'result.json'))
    if (summary.get('role')=='successor' or effective.get('role')=='successor'
            or not summary.get('component_learning_eligible') or result.get('status')!='completed'
            or effective.get('evaluation_scope')!='configured_full_clip_manifest_v1'
            or result.get('component_evaluation',{}).get('passed') is not True
            or summary['task_id']!=effective['task_id']):
        raise ValueError('qualified_normal_component_source_required_not_successor')
    runtime,output=args.runtime.resolve(),args.output.resolve()
    sys.path.insert(0,str(runtime));os.environ['KOURI_MODELS_FILE']=str(args.model_config.resolve())
    from src.rsi.feedback.capability_feedback import file_ref,verify
    from benchmarks.evolution.benchmark_script_materials import BenchmarkScriptMaterials
    from src.adapters.script_parameter_learning import learn_pending_parameters
    from src.adapters.research_luna import MODEL,MAX_TOKENS
    observations=file_ref(source/'artifact.json')
    candidates=[c for row in json.loads(verify(observations)) for c in row['candidates']
                if c['id'] in summary['component_programs']]
    if len(candidates)!=1 or candidates[0]['witness'].get('source_task_mode')!='normal_execution':
        raise ValueError('one_qualified_actual_component_program_required')
    candidate=candidates[0]
    if candidate['witness']['task_id']!=effective['task_id']:
        raise ValueError('component_source_task_binding_changed')
    for reference in [*summary['source'],*summary['boundary_evidence']]:verify(reference)
    evidence=[file_ref(trial/'effective.json'),file_ref(trial/'result.json'),
              file_ref(trial/'component-evaluation.json'),*[file_ref(p) for p in args.feedback]]
    output.mkdir(parents=True,exist_ok=False)
    configuration={'operation':'original_learn_pending_parameters','source':observations,
        'source_program_id':candidate['id'],'source_scope':'configured_full_clip_manifest_v1',
        'execution_mode':'paid' if args.call_model else 'preview','adaptation_evidence':evidence,
        'runtime_manifest':file_ref(runtime/'source-manifest.json'),
        'learner':file_ref(runtime/'src/adapters/script_parameter_learning.py'),
        'prompt':file_ref(runtime/'config/script-parameter-learning.txt'),
        'scene_adapter':file_ref(Path(__file__)),'model':MODEL,'reasoning_effort':'none',
        'max_completion_tokens':MAX_TOKENS,'model_config':file_ref(args.model_config),
        'cumulative_ledger':str(args.ledger_root.resolve()/'cost-ledger.jsonl'),
        'budget_usd':None,'request_limit':None,'reset_cumulative_ledger':False,
        'quality_scope':'source_equivalence_and_parameter_probes; independent_video_quality_unmeasured'}
    (output/'effective.json').write_text(json.dumps(configuration,indent=2)+'\n')
    if not args.call_model:return {'status':'preview',**configuration}
    if args.env_file:
        for line in args.env_file.read_text().splitlines():
            if line.startswith('KOURI_API_KEY='):
                os.environ.setdefault('KOURI_API_KEY',line.split('=',1)[1].strip().strip('"').strip("'"))
    from src.adapters.harness.capability.capability_proposal import CumulativeProposalGate
    materials=BenchmarkScriptMaterials(args.owner,args.store)
    started=time.monotonic();outcome={}
    with CumulativeProposalGate(args.ledger_root,model=MODEL,max_tokens=MAX_TOKENS,reasoning_effort='none') as gate:
        try:
            outcome=learn_pending_parameters(candidate,materials.materials,gate,output/'native',
                source_evidence=observations,adaptation_evidence=evidence)
        except Exception as error:
            outcome={'status':'failed','error':type(error).__name__+':'+str(error)}
    paths={Path(path) for path in gate.attribution.values() if Path(path).is_relative_to(output)}
    costs=[gate.costs(path) for path in sorted(paths)]
    ids=sorted({rid for cost in costs for rid in cost['request_ids']})
    outcome={**outcome,'native_registration_model_requests':outcome.get('model_requests'),
        'model_requests':len(ids),'provider_requests':len(ids),'request_ids':ids,
        'observed_model_usd':sum(c['observed_model_usd'] for c in costs)
            if all(c['observed_model_usd'] is not None for c in costs) else None,
        'billing_usd':None,'proposal_attempts_at_gate_close':costs,
        'elapsed_seconds':time.monotonic()-started,'quality_scope':configuration['quality_scope']}
    (output/'result.json').write_text(json.dumps(outcome,indent=2)+'\n')
    if outcome['status']=='registered':
        (output/'shared-catalog.json').write_text(json.dumps(materials.catalog(),indent=2)+'\n')
    return outcome


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--runtime',required=True,type=Path)
    sub=p.add_subparsers(dest='action',required=True)
    x=sub.add_parser('extract');x.add_argument('--trial',required=True,type=Path);x.add_argument('--output',required=True,type=Path)
    q=sub.add_parser('qualify-plan')
    for field in ('source','report','output'):q.add_argument('--'+field,required=True,type=Path)
    c=sub.add_parser('certify')
    for field in ('source','validation','store','output'):c.add_argument('--'+field,required=True,type=Path)
    c.add_argument('--owner',required=True)
    c.add_argument('--admission',choices=['task','component'],default='task')
    l=sub.add_parser('parameterize')
    for field in ('source','trial','store','output','ledger-root','model-config'):
        l.add_argument('--'+field,required=True,type=Path)
    l.add_argument('--env-file',type=Path);l.add_argument('--owner',required=True)
    l.add_argument('--feedback',type=Path,action='append',default=[])
    l.add_argument('--call-model',action='store_true')
    a=p.parse_args()
    result=(qualify_plan(a.runtime,a.source,a.report,a.output) if a.action=='qualify-plan' else
            parameterize(a) if a.action=='parameterize' else extract(a.runtime,a.trial,a.output)
            if a.action=='extract' else certify(a.runtime,a.source,a.validation,a.store,a.output,a.owner,a.admission))
    print(json.dumps(result,ensure_ascii=False,indent=2))
