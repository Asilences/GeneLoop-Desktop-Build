"""Scene IO for the existing Harness and cumulative gate, not another Agent loop.

Adapted from the original private run-video-task.py. Video bytes stay outside
the small program namespace; genuine pre/post snapshots go to the old learner.
"""
from __future__ import annotations
import argparse
import hashlib
import json
import os
import re
from pathlib import Path
import shutil
import subprocess
import sys
import threading
import time
from uuid import uuid4

SCENE = Path(__file__).resolve().parent


def save(path, value):
    Path(path).write_text(json.dumps(value, ensure_ascii=False, indent=2)+'\n')


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def baseline_recovery_policy(args, prior, previous, roles, parent, runtime):
    """One explicit failed-baseline repair; never another learning example."""
    report_path=getattr(args,'baseline_recovery_report',None)
    if report_path is None:
        return None
    report=json.loads(report_path.read_text())
    remaining=prior.get('timeout_seconds',0)-previous.get('elapsed_seconds',0)
    valid=(args.role==prior.get('role')=='successor'
        and prior.get('mode')=='baseline_empty_store' and args.store is not None
        and getattr(args,'component_only',False)
        and roles.get('evaluation_role')==prior.get('evaluation_role')=='fixed_decision_execution_successor_paired'
        and roles.get('evaluation_scope')==prior.get('evaluation_scope')=='configured_full_clip_plan_v1'
        and not prior.get('continuation') and prior.get('runtime')==str(runtime)
        and args.image==prior.get('image') and 0<args.timeout<=remaining+1e-6
        and args.goal_file is not None and getattr(args,'instance_file',None) is not None
        and args.model_config is not None
        and sha(args.model_config)==sha(parent/'source-snapshot/model-config.json')
        and sha(args.native_tools)==prior.get('native_tools_sha256')
        and sha(args.goal_file)==sha(parent/'source-snapshot/component-goal.txt')
        and sha(args.roles)==sha(parent/'source-snapshot/roles.json')
        and sha(args.instance_file)==sha(parent/'workspace/code/instance.json')
        and report.get('passed') is False
        and report.get('scope')=='configured_full_clip_manifest_v1'
        and report.get('evaluator_sha256')==sha(SCENE/'component_quality.py')
        and report.get('inputs',{}).get('manifest',{}).get('sha256')==sha(parent/'media-workspace/output/solution.json')
        and report.get('inputs',{}).get('media_metadata',{}).get('sha256')==prior.get('media_metadata_sha256'))
    if not valid:
        raise ValueError('same_failed_fixed_execution_baseline_one_recovery_required')
    return {'scope':'secondary_repair_inclusive_same_baseline_not_new_successor',
        'quality_failure':{'path':str(report_path.resolve()),'sha256':sha(report_path)},
        'prior_elapsed_seconds':previous['elapsed_seconds'],'remaining_seconds':remaining,
        'maximum_recovery_stages':1,'learning_eligible':False,
        'original_primary_result_preserved':True}


def media_array_view(metadata):
    """Lossless rows: current filenames are values, not JSON schema keys."""
    def order(name):
        stem = Path(name).stem
        return (0, int(stem), name) if stem.isdigit() else (1, 0, name)
    rows = []
    for name in sorted(metadata, key=order):
        item = metadata[name]
        if not isinstance(item, dict) or 'name' in item:
            raise ValueError('media_record_name_must_remain_unambiguous')
        rows.append({'name': name, **item})
    return rows


def prompt_for(instruction):
    return instruction + '''
Adapter workspace: /workspace/program is inside this same isolated task workspace.
Raw clips remain in /workspace/materials; measured media metadata is available at
/workspace/program/inputs/media.json. Its lossless array view is
/workspace/program/inputs/media-records.json: each row carries its actual filename
as name and all the same measured fields. A reusable data program can read these
measurements directly and look up the current chosen IDs/order, rather than asking
the model to transcribe measured durations into a second configuration. Current
choices and task-specific options still belong in the current input. The original
media.json remains available. Frames/contact sheets belong in /workspace/work,
so large media does not obscure the small program/input files. read_image accepts both.
Use compact JPEG contact sheets (about 960 pixels wide) for the initial overview;
the original videos remain available for any necessary detailed quality inspection.
Give every cell its ACTUAL clip ID and sample timestamp, preserve explicit numeric
ordering, and normalize each thumbnail separately to the same cell dimensions
before tiling. Mixed thumbnail dimensions can reset a montage and silently leave
cells black. Inspect the generated sheet and confirm all candidates are represented;
never infer clip IDs from positions in an unlabelled or incomplete montage.
For full-clip timing, use the measured video_duration_seconds (or the video stream's
duration). duration_seconds/container_duration_seconds describe the container and
can include trailing audio; do not substitute that value for a known video duration.
Preserve the selected clips' native frame geometry and timebase when assembling the
delivered video. Thumbnail normalization is not a reason to resize the final video.
Avoid unnecessary scaling, filters or lossy transformations; inspect source/output
frame correspondence and timing if encoding or format conversion is required.
Codec compatibility must not replace the storyboard judgment about which clip to use.
If selected inputs have different frame rates, use an explicit constant frame rate
for the delivered video and verify timestamp correspondence; unconstrained concat
can create a variable-rate stream whose average rate misleads frame seeking.
The task container has 2 CPUs and 4 GiB of RAM. Avoid an unnecessary full re-encode;
if conversion is needed, choose a practical preset and verify the required fidelity.
Equal codec/resolution/frame rate alone does not prove stream-copy timing is safe.
The concat demuxer may use container durations that include audio padding. When a
full-clip timeline uses measured video durations, account explicitly for those
durations in its concat data when appropriate, then verify the actual output clock.
Inspect each video stream's start_time too: concat duration directives do not zero
per-file video PTS offsets. For sources measured at one common frame rate, a dense
decoded-frame clock can avoid spurious CFR duplication; verify the complete source
frame count and correspondence. Filter reinitialization on changed frame metadata
can reset frame counters. Mixed-rate sources need their own clock conversion;
do not apply a common-native-frame-rate assumption to them.

Use the overview to identify plausible candidates. Before the first encode, compare
beginning/middle/end frames where the requested action, fade or camera movement
distinguishes those candidates; a single still cannot establish motion. Then complete
a first playable draft and its manifest, and correct concrete uncertainties.
Keep all attempts. The final output must satisfy every original storyboard and video
requirement; a draft or a tool success is not final quality evidence. Choose clips
and their order yourself from the supplied pixels, never from outside answers.

Separate decisions that need CURRENT judgment from the stable computations that
execute those decisions. If a certified-operation catalog is supplied, inspect its
interfaces before writing a new implementation. Choose a suitable existing operation
or implement the missing behavior; no operation is mandatory. A manifest computation
does not decide which clips match the storyboard. You still own the current choices.
For an Artifact call using value/output, the output path belongs to its private
native workspace, for example /work/outputs/result. export_directory delivers the
generated files to a current container directory such as /workspace/output.
For any new program you need, organize current-instance JSON data separately from
the executable processing. Design its data interface and algorithms yourself.
Keep clip choices and measurements
in JSON rather than embedding them in a fresh program for each instance.
Before writing the implementation, collect all CURRENT context-dependent values in
one configuration/input section. At the start of the program, read that configuration
into named variables; keep the reusable processing functions below it. Read current
clip paths, selection/order, timing and any task-specific output options from those
variables. Do not scatter current-instance literals through function bodies or fix
the number of clips in the algorithm. Include only options this task actually needs.
The inputs/media.json file is read-only; put your decision JSON beside your program
under /workspace/program. Do not store
Python source or executable expressions in JSON. Keep deterministic data processing
separate from external media commands; ffmpeg/ffprobe remain ordinary tools. Document
the JSON interface in the program docstring. A standalone data-processing Python
program should take its explicitly witnessed current JSON input file(s), followed
by a fresh output directory, as positional arguments. These can include a decision
file and the prepared measurement file; multiple native input slots already exist.
Declare the actual input order in your program's docstring. Invoke it in its own
execute call without mkdir/cd or trailing shell checks,
so its actual input/output and execution can be inspected independently. Its output
directory is under /workspace/program/outputs. execute starts in /workspace/program;
Pass an output directory that does not exist yet and let the program create it;
do not pre-create that output directory in an earlier shell call.
use relative operands for that program invocation. For a program declaring a decision
file, a measurement file and an output directory, an example is python3 edit.py
instance.json inputs/media-records.json outputs/draft; use your actual declared interface.
Supply current files through those explicit JSON/argv input slots instead of
hardcoded input/output paths or undeclared environment-dependent reads. Reading
the prepared measurement file through its own witnessed input slot is supported. That
data-processing program must generate only small data/text files, without subprocess,
cv2 or media execution. Run external media commands separately and store large video
intermediates under /workspace/work, outside the small program/output namespace.
Original final deliverables still go
to /workspace/output/solution.mp4 and /workspace/output/solution.json.
The code-organization convention applies to new code you actually need; it does not
require reimplementing a suitable existing computation.
Inspect your final files, then reply only with the two delivered paths.
'''


def run(args):
    if getattr(args,'baseline_recovery_report',None) is not None and not args.continue_trial:
        raise ValueError('baseline_recovery_requires_finished_parent_and_followup')
    runtime = args.runtime.resolve()
    sys.path.insert(0, str(runtime))
    if args.model_config:
        os.environ['KOURI_MODELS_FILE']=str(args.model_config.resolve())
    from src.adapters.harness.capability.capability_proposal import CumulativeProposalGate, MODEL, MAX_TOKENS
    from src.adapters.harness.harness_runtime import create_harness
    provider, effort = 'deepseek-official', 'off'
    luna = args.model=='gpt-6-luna'
    if luna:
        if not args.model_config:
            raise ValueError('luna_requires_explicit_isolated_model_config')
        from src.adapters.research_luna import MODEL, MAX_TOKENS, PROVIDER, harness_patch
        provider, effort = PROVIDER, 'none'
    if args.env_file:
        for line in args.env_file.read_text().splitlines():
            if line.startswith('KOURI_API_KEY='):
                os.environ.setdefault('KOURI_API_KEY', line.split('=', 1)[1].strip().strip('"').strip("'"))
    task = args.official/'tasks'/('agentic_vbench_'+args.family)/('agentic-vbench-'+args.family+'-task'+str(args.task))
    roles=json.loads(args.roles.read_text())
    frozen_role=roles['tasks'].get(task.name)
    allowed={'development_source_retest':('development','learning'),'certification':('certification',),
             'sealed_successor_paired':('successor',),'sealed_applicability':('successor',)}
    if args.role not in allowed.get(frozen_role,()):
        raise ValueError('task_role_differs_from_frozen_study')
    if args.reference_program and args.role!='certification':
        raise ValueError('ordinary_reference_program_is_certification_only')
    instruction = task/'steps/solve/instruction.md'
    directory = args.output.resolve()
    directory.mkdir(parents=True, mode=0o700, exist_ok=False)
    source = directory/'source-snapshot'; source.mkdir()
    for path in (Path(__file__), args.native_tools, runtime/'src/adapters/deepseek_cost_gate.py',
                 runtime/'src/adapters/harness/capability/capability_proposal.py'):
        shutil.copyfile(path, source/path.name)
    if luna:
        shutil.copyfile(runtime/'src/adapters/research_luna.py',source/'research_luna.py')
        shutil.copyfile(args.model_config,source/'model-config.json')
    shutil.copyfile(args.roles,source/'roles.json')
    if args.store:
        shutil.copyfile(SCENE/'capability_tools.ts',source/'capability_tools.ts')
    workspace, media = directory/'workspace', directory/'media-workspace'
    for path in (workspace/'inputs', workspace/'code', workspace/'outputs/code',
                 media/'materials', media/'work', media/'output', media/'program'):
        path.mkdir(parents=True)
    prompt = prompt_for(instruction.read_text())
    component_only=getattr(args,'component_only',False)
    component_scope=roles.get('evaluation_scope') if component_only else None
    if component_only:
        if args.goal_file is None:
            raise ValueError('component_goal_file_required')
        if component_scope not in ('configured_full_clip_manifest_v1','configured_full_clip_plan_v1'):
            raise ValueError('separate_component_study_required')
        prompt=args.goal_file.read_text()
        shutil.copyfile(args.goal_file,source/'component-goal.txt')
        shutil.copyfile(SCENE/'component_quality.py',source/'component_quality.py')
    session_id, context_directory, dsh_home, continuation = None, directory, directory/'dsh', None
    recovery=None
    if args.continue_trial:
        parent=args.continue_trial.resolve()
        prior=json.loads((parent/'effective.json').read_text())
        previous=json.loads((parent/'result.json').read_text())
        recovery=baseline_recovery_policy(args,prior,previous,roles,parent,runtime)
        development=args.role==prior['role']=='development'
        if (not (development or recovery is not None) or args.followup is None
                or prior['task_id']!=task.name or prior['model']!=MODEL
                or prior['task_sha256']!=sha(instruction)
                or previous['status'] not in ('completed','failed','incomplete')):
            raise ValueError('same_finished_development_task_and_model_required_for_continuation')
        previous_home=Path(prior.get('dsh_home',str(parent/'dsh')))
        sessions=list((previous_home/'sessions').glob('*/agentic-vbench-*'))
        if len(sessions)!=1:
            raise ValueError('one_original_development_session_required')
        # The pinned SDK cannot reopen a persisted session: session/prompt
        # always creates on first use. Continue the same task with its files
        # through the ordinary fresh-session entry, preserving the old history.
        shutil.copytree(sessions[0],directory/'prior-session',ignore=shutil.ignore_patterns('*.lock'))
        for name in ('workspace','media-workspace'):
            shutil.copytree(parent/name,directory/name,dirs_exist_ok=True,symlinks=True)
        # Prior renders belong to media, not the new bounded program boundary.
        # Relocate only the copied output tree; old evidence/bytes stay intact.
        prior_outputs=workspace/'outputs/code'
        archive=media/'work/previous-program-outputs'/parent.name
        archive.parent.mkdir(parents=True,exist_ok=True)
        if archive.exists():
            raise ValueError('continuation_media_archive_already_exists')
        shutil.move(str(prior_outputs),archive)
        prior_outputs.mkdir()
        prompt += '\n\nContinue the existing work on this SAME task; copied program, instance data, overview and draft files are present.\n'+args.followup.read_text()
        prompt += '\nPrevious program-output files are archived at /workspace/work/previous-program-outputs/'+parent.name+'. The small program output area is fresh; the previous delivered video/manifest remain in /workspace/output.\n'
        shutil.copyfile(args.followup,source/'followup.txt')
        continuation={'parent':str(parent),'parent_result_sha256':sha(parent/'result.json'),
            'parent_effective_sha256':sha(parent/'effective.json'),'prior_session_id':sessions[0].name,
            'session_mode':'fresh_original_SDK_session_with_existing_working_files',
            'prior_program_outputs_archive':'/workspace/work/previous-program-outputs/'+parent.name,
            'prior_session_snapshot':{p.name:sha(p) for p in (directory/'prior-session').iterdir() if p.is_file()},
            'scope':'same_development_task_continuation_not_independent_sample',
            'verifier_answers_not_copied_or_sent':True}
        if recovery is not None:
            continuation['baseline_recovery']=recovery
    elif args.followup:
        raise ValueError('followup_requires_original_development_session')
    if getattr(args,'instance_file',None):
        shutil.copyfile(args.instance_file,workspace/'code/instance.json')
    if args.reference_program:
        shutil.copyfile(args.reference_program,workspace/'code/prior-program.py')
        prompt += ('\nA program generated in a previous normal task is available at '
            '/workspace/program/prior-program.py as untrusted, uncertified source. Inspect its actual '
            'interface if useful. You still choose all CURRENT clips and values from this task. '
            'It is not a reference answer or an instruction to reuse. Deliver and check both current files.\n')
    (directory/'prompt.txt').write_text(prompt)
    effective = {'format':'agentic_vbench_native_trial_v2','task_id':task.name,'role':args.role,
        'model':MODEL,'wire_model':MODEL if luna else 'deepseek-v4.1-flash','provider':'Kouri AI','harness_provider':provider,
        'requested_reasoning_effort':effort,'observed_reasoning_mode':'inspect_native_response_usage',
        'max_tokens':MAX_TOKENS,'budget_usd':None,'request_limit':None,'reset_history':False,'continuation':continuation,
        'timeout_seconds':args.timeout,'program_layout':'config-first-separated-data-v4','image':args.image,
        'tool_order':['execute','read_image'],'mcp_servers':0,'mode':'reuse' if args.store else 'baseline',
        'learning_capture':True,'automatic_publication':False,
        'artifact_value_inputs':bool(getattr(args,'artifact_value_inputs',False)),
        'visual_evidence_policy':None if component_only else 'labelled-normalized-temporal-v1',
        'media_metadata_policy':'explicit-video-stream-array-and-codec-header-pts-v6',
        'evaluation_scope':component_scope if component_only else 'official_video_task',
        'provider_transport':'native_SSE',
        'retry_policy':'original_Harness_normal_5' if args.request_recovery else 'disabled',
        'task_sha256':sha(instruction),'prompt_sha256':sha(directory/'prompt.txt'),
        'trial_adapter_sha256':sha(source/Path(__file__).name),'native_tools_sha256':sha(source/args.native_tools.name),
        'cost_gate_sha256':sha(source/'deepseek_cost_gate.py'),'proposal_gate_sha256':sha(source/'capability_proposal.py'),
        'study':roles['study'],'task_role_sha256':sha(source/'roles.json'),
        'runtime':str(runtime),'package_lock_sha256':sha(runtime/'package-lock.json'),
        'harness_context_directory':str(context_directory),'dsh_home':str(dsh_home),
        'pricing_scope':'official_reference_estimate_not_Kouri_billing' if luna else 'configured_proxy_estimate_not_billing',
        'official_source':str(task),'material_and_environment_reuse':'official prebuilt media image, no oracle mounted'}
    save(directory/'effective.json',effective)
    if roles.get('evaluation_role'):
        effective['evaluation_role']=roles['evaluation_role']
        save(directory/'effective.json',effective)
    if args.reference_program:
        effective['ordinary_reference_program_sha256']=sha(workspace/'code/prior-program.py')
        save(directory/'effective.json',effective)
    if not args.call_model:
        return {'status':'preview','directory':str(directory),'effective':effective}
    container='geneloop-avb-'+uuid4().hex[:12]
    result={'status':'failed','quality':'pending_official_verifier','provider_requests':None}
    started=time.monotonic()
    gate=None
    def command(argv,**kw):
        return subprocess.run(argv,text=True,capture_output=True,check=True,**kw)
    try:
        command(['docker','run','-d','--name',container,'--network','none','--cpus','2','--memory','4g',
            '-v',str(media)+':/workspace','-v',str(workspace/'code')+':/workspace/program',
            '-v',str(workspace/'inputs')+':/workspace/program/inputs:ro',
            '-v',str(workspace/'outputs/code')+':/workspace/program/outputs',
            '-w','/workspace/program',args.image,'sleep','infinity'])
        effective['image_id']=command(['docker','inspect','--format','{{.Image}}',container]).stdout.strip()
        command(['docker','exec',container,'bash','-lc','cp -a /baked/materials/. /workspace/materials/'])
        # Raw tool measurements are identical context in both arms, never picks.
        probe="""import glob,json,subprocess,os
out={}
for p in glob.glob('/workspace/materials/*.mp4'):
 v=json.loads(subprocess.check_output(['ffprobe','-v','error','-show_streams','-show_format','-show_data_hash','sha256','-of','json',p]))
 keys=('index','codec_type','codec_name','codec_tag_string','profile','level','pix_fmt','width','height',
  'color_space','color_range','color_transfer','color_primaries','sample_aspect_ratio','field_order','extradata_hash',
  'avg_frame_rate','r_frame_rate','time_base','start_time','duration','duration_ts','nb_frames','sample_rate','channels','channel_layout')
 video=next((s for s in v['streams'] if s.get('codec_type')=='video'),{})
 duration=video.get('duration')
 out[os.path.basename(p)]={'path':p,'duration_seconds':float(v['format']['duration']),
  'container_duration_seconds':float(v['format']['duration']),
  'video_duration_seconds':float(duration) if duration not in (None,'N/A') else None,
  'streams':[{k:s[k] for k in keys if k in s} for s in v['streams']]}
print(json.dumps(out))"""
        measured=command(['docker','exec',container,'python3','-c',probe])
        (workspace/'inputs/media.json').write_text(measured.stdout)
        save(workspace/'inputs/media-records.json',media_array_view(json.loads(measured.stdout)))
        effective['inputs_sha256']={p.name:sha(p) for p in (media/'materials').iterdir() if p.is_file()}
        effective['media_metadata_sha256']=sha(workspace/'inputs/media.json')
        effective['media_array_metadata_sha256']=sha(workspace/'inputs/media-records.json')
        if recovery is not None and any(effective.get(key)!=prior.get(key) for key in
                ('image_id','inputs_sha256','media_metadata_sha256','media_array_metadata_sha256')):
            raise ValueError('baseline_recovery_original_materials_changed')
        save(directory/'media-view-provenance.json',{'format':'video_media_array_view_v1',
            'source':{'path':'workspace/inputs/media.json','sha256':effective['media_metadata_sha256']},
            'view':{'path':'workspace/inputs/media-records.json','sha256':effective['media_array_metadata_sha256']},
            'filenames_are_row_values':True,'measured_values_changed':False})
        capability_dispatch, capability_receipts, trial_view = None, [], None
        if args.store:
            from benchmarks.evolution.benchmark_script_materials import BenchmarkScriptMaterials
            from benchmarks.evolution.benchmark_capability_tools import benchmark_capability_tools, capability_invocation_view
            from benchmarks.evolution.skillsbench_trial import SkillsBenchTrial
            # Reuse original delivery operations, not a second Capability executor.
            class PreparedVideoView(SkillsBenchTrial):
                def __init__(self):
                    self.output=directory/'delivery-operations';self.output.mkdir()
                    self.container=container;self.prepared=True;self.evaluated=False;self.operation=0
                    self._run_command=subprocess.run
                    self._manifest={'input_fingerprint':hashlib.sha256(json.dumps(effective['inputs_sha256'],sort_keys=True).encode()).hexdigest(),
                                    'source_identity':effective['task_sha256']}
            trial_view=PreparedVideoView()
            shutil.copytree(args.store,directory/'frozen-store')
            manager=BenchmarkScriptMaterials(args.owner,directory/'frozen-store',
                artifact_value_inputs=effective['artifact_value_inputs'])
            catalog=manager.catalog()
            if recovery is not None and (catalog['snapshot']['roots'] or
                    catalog['snapshot']['digest']!=prior.get('frozen_capability_snapshot')):
                raise ValueError('baseline_recovery_requires_original_empty_snapshot')
            # An empty original Store is the paired Baseline. It exposes the
            # same native tool schemas without offering learned operations.
            effective['mode']='reuse' if catalog['snapshot']['roots'] else 'baseline_empty_store'
            save(directory/'frozen-capability-context.json',catalog)
            native,capability_dispatch,capability_receipts=benchmark_capability_tools(manager,trial_view,
                directory/'capability-calls',task.name+'-'+directory.name)
            save(directory/'capability-tools.json',native)
            (directory/'capability-replies').mkdir()
            effective['tool_order'] += [tool['name'] for tool in native]
            effective['frozen_capability_snapshot']=catalog['snapshot']['digest']
            by_id={cap['id']:cap for cap in catalog['snapshot']['capabilities']}
            prompt += '\nAvailable certified operations, chosen only when suitable for the CURRENT input:\n'+json.dumps([
                {'capability_id':card['capability']['id'],'description':card.get('description'),
                 **capability_invocation_view(by_id[card['capability']['id']],card)}
                for card in catalog.get('catalog',[])],ensure_ascii=False)
            (directory/'prompt.txt').write_text(prompt)
            effective['prompt_sha256']=sha(directory/'prompt.txt')
        save(directory/'effective.json',effective)
        patch=directory/'native.patch.yml'
        system_policy=('After a labelled overview covering every candidate and the necessary temporal '
            'checks for requested actions or camera movement, produce and run your current best '
            'complete draft, including BOTH the video and its manifest. '
            'Choose suitable existing computations or author the missing behavior; no operation is mandatory. '
            'Then inspect and improve concrete defects until the original task requirements are satisfied. '
            'Do not spend the entire task in diagnosis without a deliverable. You own every current clip '
            'selection and ordering decision. Keep messages between necessary tool calls brief.')
        if component_only:
            system_policy=('Complete the current configured-manifest task with actual current files. '
                'Context-dependent values belong in instance.json and are read at program entry. '
                'Use a fresh output directory that does not exist yet; run the standalone data program '
                'in its own execute call. Keep data processing separate from media execution. '
                'Existing certified operations are optional when suitable. Inspect and deliver '
                '/workspace/output/solution.json. This task does not select storyboard matches or render a video.')
            if component_scope=='configured_full_clip_plan_v1':
                system_policy=('Complete the supplied current video-project task with real files. '
                    'Keep current choices/options in data and read actual measurements from the prepared inputs. '
                    'Pure data generation and ordinary media execution remain separate. Use existing code '
                    'or certified operations when suitable; no operation is mandatory. Actually consume '
                    'the generated plan and deliver both the new video and manifest. Independent plan '
                    'checks are pending; do not claim official storyboard quality from this project task.')
        effective['system_policy']=system_policy
        save(directory/'effective.json',effective)
        rows=[{'id':'system-prompt','config':{'personaPrefix':'Complete the supplied video task with the available native tools in its isolated container.',
            'personaSuffix':system_policy}},
            {'insert':[{'id':'research-native-tools','name':(source/args.native_tools.name).as_uri()}]}]
        if args.request_recovery:
            rows.append({'id':'llm-retry','disabled':False})
        if args.store:
            rows.append({'insert':[{'id':'agentic-vbench-capability-tools','name':(source/'capability_tools.ts').as_uri()}]})
        patch.write_text('\n'.join('- '+json.dumps(row) for row in rows)+'\n')
        with CumulativeProposalGate(args.ledger_root,
                model=MODEL,max_tokens=MAX_TOKENS,reasoning_effort=effort) as gate:
            gate.current=directory
            env={**gate.environment(),'GENELOOP_RESEARCH_CONTAINER':container,
                'GENELOOP_RESEARCH_WORKSPACE':str(workspace),'GENELOOP_RESEARCH_RUN':str(directory),
                'GENELOOP_RESEARCH_WORKDIR':'/workspace/program',
                'GENELOOP_RESEARCH_IMAGE_ROOTS':json.dumps([{'virtual':'/workspace','host':str(media)}]),
                'GENELOOP_RESEARCH_EXECUTE_DESCRIPTION':'Run a shell command in this isolated video task. Python, ffmpeg, ffprobe, NumPy and OpenCV are available.',
                'DSH_HOME':str(dsh_home),'SSS_SCENARIO_TOOLS':json.dumps(effective['tool_order'])}
            if luna:
                rows.append(harness_patch(env['DEEPSEEK_BASE_URL']))
                env['KOURI_MODELS_FILE']=str(args.model_config.resolve())
                patch.write_text('\n'.join('- '+json.dumps(row) for row in rows)+'\n')
            if args.store:
                env.update(GENELOOP_VIDEO_CAPABILITY_TOOLS=str(directory/'capability-tools.json'),
                    GENELOOP_VIDEO_CAPABILITY_REPLIES=str(directory/'capability-replies'))
            def observe(notification):
                if notification.method=='session.event':
                    with (directory/'events.jsonl').open('a') as stream:
                        stream.write(json.dumps(notification.payload.get('event'),ensure_ascii=False)+'\n')
                    event=notification.payload.get('event') or {}
                    data=event.get('data',{})
                    if capability_dispatch is not None and event.get('type')=='tool/call' and data.get('name') in ('capability_list','capability_call'):
                        if not re.fullmatch(r'[A-Za-z0-9_-]{1,200}',data.get('callId','')):
                            raise ValueError('video_capability_transport_call_invalid')
                        arguments=data['arguments']
                        if isinstance(arguments,str):arguments=json.loads(arguments)
                        reply={'call_id':data['callId'],'name':data['name'],'arguments':arguments}
                        try:reply['value']=capability_dispatch(data['name'],arguments)
                        except Exception as error:reply['error']=type(error).__name__+':'+str(error)
                        target=directory/'capability-replies'/(data['callId']+'.json')
                        pending=target.with_suffix('.tmp');save(pending,reply);pending.replace(target)
            try:
                with create_harness(root=runtime,patches=(str(runtime/'config/semantic-sdk.patch.yml'),str(patch)),env=env,
                    provider=provider,model=MODEL,max_tokens=MAX_TOKENS,cwd=str(context_directory),
                    runtime_cwd=str(directory),request_timeout_seconds=args.timeout) as client:
                    def cancel():
                        result['timed_out']=True
                        # Pinned SDK lacks session/cancel. Close this owned runtime.
                        client.close()
                        save(directory/'cancel.json',{'method':'owned_runtime_close','runtime_closed':True,'timeout_seconds':args.timeout})
                    timer=threading.Timer(args.timeout,cancel);timer.daemon=True;timer.start()
                    try:
                        reply=client.run(prompt,session_id=session_id or 'agentic-vbench-'+uuid4().hex,on_notification=observe)
                        (directory/'answer.txt').write_text(reply.final_response or '')
                        result.update(status='completed' if reply.finish_reason=='completed' else 'incomplete',finish_reason=reply.finish_reason)
                    finally:
                        timer.cancel();timer.join()
            except Exception as error:
                result['error']=type(error).__name__+':'+str(error)
            finally:
                result.update(gate.costs(directory))
        # A cancelled downstream can leave an upstream response settling later.
        # Preserve this snapshot; sample once more after verifier/cleanup below.
        result.update(gate.costs(directory))
        # The pinned Harness sorts registered tools before the provider request.
        # Record the actual wire schema instead of treating registration order
        # as the order observed by the model. Historical snapshots stay intact.
        wire_schemas=[json.loads(p.read_text()).get('tools') for p in sorted(directory.glob('request-*.json'))]
        wire_schemas=[value for value in wire_schemas if value is not None]
        if wire_schemas:
            encoded=[json.dumps(value,sort_keys=True,separators=(',',':')).encode() for value in wire_schemas]
            effective['registered_tool_order']=effective['tool_order']
            effective['actual_wire_tool_order']=[t.get('function',t)['name'] for t in wire_schemas[0]]
            effective['actual_wire_tool_schema_sha256']=hashlib.sha256(encoded[0]).hexdigest()
            effective['wire_tool_schemas_consistent']=all(raw==encoded[0] for raw in encoded)
            save(directory/'effective.json',effective)
        result['output_files']={p.name:{'sha256':sha(p),'bytes':p.stat().st_size} for p in (media/'output').iterdir() if p.is_file()}
        if args.store:
            trial_view.evaluated=True
            save(directory/'capability-call-records.json',capability_receipts)
            result['capability_calls']=len(capability_receipts)
        # Freeze solver results before allowing the independent verifier access.
        save(directory/'pre-verification.json',result)
        if component_only:
            if component_scope=='configured_full_clip_plan_v1':
                result['component_evaluation']={'status':'pending_independent_plan_checks',
                    'scope':component_scope,'passed':None}
                result['evaluation']={'status':'not_evaluated','scope':'official_video_task','end_to_end_attempted':False}
                result['quality']='pending_independent_plan_checks'
                return result
            import importlib.util
            spec=importlib.util.spec_from_file_location('video_component_quality',source/'component_quality.py')
            evaluator=importlib.util.module_from_spec(spec);spec.loader.exec_module(evaluator)
            component=evaluator.evaluate(workspace/'code/instance.json',media/'output/solution.json',workspace/'inputs/media.json')
            save(directory/'component-evaluation.json',component)
            result['component_evaluation']={**component,'record_sha256':sha(directory/'component-evaluation.json')}
            result['evaluation']={'status':'not_evaluated','scope':'official_video_task','end_to_end_attempted':False}
            result['quality']='configured_manifest_only'
            return result
        if result.get('timed_out'):
            command(['docker','stop','--time','0',container]);command(['docker','start',container])
        command(['docker','cp',str(task/'steps/solve/tests'),container+':/tests'])
        scored=subprocess.run(['docker','exec',container,'bash','/tests/test.sh'],capture_output=True,text=True,timeout=300)
        (directory/'verification.txt').write_text(scored.stdout+'\n'+scored.stderr)
        command(['docker','cp',container+':/logs/verifier',str(directory/'verifier')])
        reward=json.loads((directory/'verifier/reward.json').read_text())
        result['evaluation']={'reward':reward['reward'],'verifier_returncode':scored.returncode,
            'evidence_sha256':sha(directory/'verifier/reward.json'),'solver_was_finished_before_verifier':True}
        result['quality']='official_verifier'
    except Exception as error:
        result['host_error']=type(error).__name__+':'+str(error)
    finally:
        subprocess.run(['docker','rm','-f',container],capture_output=True)
        if gate is not None:
            result.update(gate.costs(directory))
            result['cost_observed_after_cleanup']=True
        result['elapsed_seconds']=time.monotonic()-started
        save(directory/'result.json',result)
    return result


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__)
    for field in ('runtime','official','output','ledger-root','native-tools'):
        p.add_argument('--'+field,required=True,type=Path)
    p.add_argument('--env-file',type=Path)
    p.add_argument('--roles',type=Path,default=SCENE/'roles.json')
    p.add_argument('--reference-program',type=Path,help='Actual ordinary source for independent certification inputs, never a successor hint')
    p.add_argument('--store',type=Path,help='Frozen original material pool; use an empty pool for the same-tool Baseline')
    p.add_argument('--request-recovery',action='store_true',help='Enable the original Harness normal request-retry plugin')
    p.add_argument('--model',choices=['deepseek-flash','gpt-6-luna'],default='deepseek-flash')
    p.add_argument('--model-config',type=Path,help='Opt-in process-only Kouri model file; production defaults are unchanged')
    p.add_argument('--continue-trial',type=Path,help='Continue the same development task from copied files using the original SDK fresh-session entry; old history stays untouched')
    p.add_argument('--followup',type=Path,help='Normal user continuation, without verifier answers; requires --continue-trial')
    p.add_argument('--baseline-recovery-report',type=Path,help='Explicit single secondary repair of a failed fixed-execution empty-store successor; original primary result stays sealed')
    p.add_argument('--component-only',action='store_true',help='Separate configured-manifest task; does not attempt or grade official video assembly')
    p.add_argument('--goal-file',type=Path,help='Explicit component task instructions, frozen in this run')
    p.add_argument('--instance-file',type=Path,help='Frozen current edit plan, identical for both successor arms')
    p.add_argument('--artifact-value-inputs',action='store_true',help='Expose the original certified Artifact JSON-value binding as well as file inputs; record explicitly in each new run')
    p.add_argument('--owner',default='agentic-vbench-efficiency-20261109-v2')
    p.add_argument('--family',choices=['assembly','sequencing'],default='assembly')
    p.add_argument('--task',required=True,type=int)
    p.add_argument('--role',required=True,choices=['development','learning','certification','successor'])
    p.add_argument('--image',required=True)
    p.add_argument('--timeout',type=float,default=1800)
    p.add_argument('--call-model',action='store_true')
    print(json.dumps(run(p.parse_args()),ensure_ascii=False,indent=2))
