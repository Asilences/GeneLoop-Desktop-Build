"""Restart the public Harness around one original durable task; never reset admission."""
import hashlib,json,os,re,threading,time
from .model_api import model_api_key_configured, model_api_root, model_sdk_key, model_routes
from pathlib import Path
from types import SimpleNamespace
from uuid import uuid4
from .continuous_rsi import ROOT,PRIVATE_HOME,private,load_config,enroll,seal,launch_worker,read,sha,source_map,reviewed_source_relocation,writer_lock
from .operation_budget import OperationBudget,command
from .scenario import prepare_file_scenario as prepare_scenario
from src.adapters.harness.harness_runtime import create_harness
from src.adapters.deepseek_cost_gate import create_file_server as create_server
from .native_budget import NativeBudgetGuard
from src.adapters.harness.dsh_client import _usage
from src.motif_core.reuse.experience_registry import durable,digest


def mcp_transport_interrupted(event):
    """Only an explicit tool error can signal transport loss, never source text."""
    if event.get('type')!='tool/result':return False
    for block in event.get('data',{}).get('message',{}).get('content',[]):
        if block.get('type')!='tool-result' or block.get('isError') is not True:continue
        for part in block.get('content',[]):
            if part.get('type')=='text' and re.search(r'connection[^\n]{0,200}closed|broken pipe|end of stream|server[^\n]{0,200}terminated|session[^\n]{0,200}closed',part.get('text',''),re.I):return True
    return False


def recovery_source_transition(origin,out,current):
    """Verify a reviewed relocation or a recorded host observer repair."""
    old=read(origin/'source-code.json')
    if old==current:return None
    relocation=reviewed_source_relocation(old,current)
    if relocation:
        if digest(old)!=read(origin/'enrollment.json').get('source_sha256'):
            raise ValueError('original enrolled code changed')
        return relocation
    file=out/'recovery-observer-transition.json';value=read(file)
    changed={n for n in set(old)|set(current) if old.get(n)!=current.get(n)}
    if ('src/adapters/operation_runner.py' not in changed or changed-{'src/adapters/operation_runner.py','src/adapters/continuous_motif_learning.py'}
            or value.get('format')!='sss-observer-recovery-transition-v1'
            or value.get('before')!=old or value.get('after')!=current
            or value.get('original_enrollment_sha256')!=sha(origin/'enrollment.json')):raise ValueError('original code changed outside recorded observer repair')
    context=read(origin/'enrollment.json');events=Path(context['job_file']+'.events')
    if not any(e.get('kind')=='host_authorized_observer_repair' and e.get('detail',{}).get('transition_sha256')==sha(file)
               for p in events.glob('*.json') if (e:=read(p))):raise ValueError('observer repair lacks original durable job event')
    return {'file':str(file),'sha256':sha(file),'scope':'observer_only_no_tool_or_permission_change'}

def initialize_job(file,task,delivery,limits):
    import sys
    sys.path.insert(0,str(ROOT/'scenarios/file-management'))
    if json.loads(Path(task).read_text()).get('management_contract'):
        from management_tools import execution_version as operation_version
    else:
        from operation_tools_v2 import operation_version
    if not Path(file).exists():command(file,'init',{'task_file':str(task),'delivery_root':str(delivery),'execution_version_sha256':operation_version(),
        'limits':{**limits,'max_requests':limits.get('max_requests',limits['max_steps'])}})
    s=command(file,'state')['state']
    if s['task_sha256']!=sha(task) or s['execution_version_sha256']!=operation_version():raise ValueError('frozen durable task/version changed')
    return s


def frozen_scene_patch(out, prepared, *, resume=False):
    """Keep the exact enrolled composition, including extra experiment plugins."""
    target=Path(out)/'scene.patch.yml';manifest=Path(out)/'scene-patch.json'
    if resume:
        if not target.exists() or not manifest.exists():
            raise ValueError('original task predates durable scene capture; explicit migration required')
        if sha(target)!=read(manifest)['sha256']:raise ValueError('original scene composition changed')
    else:
        original=Path(prepared['patch']);target.write_bytes(original.read_bytes());target.chmod(0o600)
        durable(manifest,{'original_patch':str(original),'sha256':sha(target)},exclusive=True)
    return str(target)

def relocated_scene_patch(original, attempt):
    """Rebind the entry plugin in a verified frozen patch with YAML env tags."""
    text = Path(original).read_text(encoding='utf-8')
    old_uri = (ROOT / 'src/adapters/file_entry_motif.ts').as_uri()
    if old_uri not in text:
        return original
    match = re.compile(r'\{\s*"id"\s*:\s*"sss-entry-motif"\s*,\s*"name"\s*:\s*'
                       + re.escape(json.dumps(old_uri)) + r'\s*\}')
    if len(match.findall(text)) != 1 or text.count(old_uri) != 1:
        raise ValueError('original entry Motif declaration changed')
    entry = {'id': 'sss-entry-motif', 'name': (ROOT / 'src/adapters/harness/motif/dsh_entry_motif.ts').as_uri(),
             'config': {'durablePlan': True}}
    patch = attempt / 'relocated-scene.patch.yml'
    patch.write_text(match.sub(lambda _: json.dumps(entry), text), encoding='utf-8')
    patch.chmod(0o600)
    return str(patch)


def relocated_operation_binding(original, attempt, enrolled):
    """Preserve the frozen task and registry while rebinding the reviewed launcher."""
    name = 'src/adapters/scenario.py'
    binding = read(original)
    locks = binding['runtime_source']
    if name not in locks:
        return original
    if locks[name] != enrolled.get(name):
        raise ValueError('original operation launcher binding changed')
    locks[name] = sha(ROOT / name)
    path = attempt / 'relocated-operation-binding.json'
    durable(path,binding,exclusive=True)
    return path


def relocated_rsi_patch(original, attempt, owner):
    from .daily_decision_learning import compatible_decision_config

    patch = read(original)
    for row in patch:
        for plugin in row.get('insert', []):
            if plugin.get('id') != 'geneloop-learned-decisions':
                continue
            config = plugin['config']
            current = compatible_decision_config(config, attempt, owner=owner)
            if current == config:
                return original
            plugin['config'] = current
            path = attempt / 'relocated-rsi.patch.yml'
            durable(path,patch,exclusive=True)
            return path
    return original


def execute(args,prepared=None,*,on_event=None,on_start=None):
    import sys
    from .file_provider import configured,attach,platform_headers
    provider=None
    if not args.call_model and not args.rsi_resume:return {'paid':False,'original_limits':load_config(args.rsi_config)['limits']}
    if args.rsi_resume:
        origin=private(args.rsi_resume);context=read(origin/'enrollment.json');out=private(context['out']);cfg=context['config'];job=private(context['job_file'])
        provider=configured() if cfg['provider_mode']=='real' else None
        if context.get('provider_binding')!=(provider['provider_binding'] if provider else None):raise ValueError('original File provider binding changed; use a new task version')
        transition=recovery_source_transition(origin,out,source_map())
        if digest(read(context['task_file']))!=digest(read(origin/'task.json')):raise ValueError('original task changed; recovery refused')
        original=context['arguments'];args=SimpleNamespace(**{**vars(args),**original,'rsi_config':Path(cfg['config_file']),'scenario':Path(context['scenario_file'])})
        # Preserve the original native tool surface even outside a Web process.
        # A host-issued todo tool was present in some ordinary CLI enrollments.
        original_tools=read(out/'rsi-binding.json')['allowed_tools']
        prepared=prepare_scenario(args.scenario,web_deployment=bool(os.environ.get('SSS_WEB_POLICY')) or 'todo_write' in original_tools)
        if sha(args.scenario)!=context['scenario_sha256'] or digest(prepared['prompt'])!=context['prompt_sha256']:raise ValueError('original scenario/prompt changed; recovery refused')
        env={'FM_TASK_FILE':context['task_file'],'FM_OUTPUT':context['delivery'],'FM_JOB_FILE':str(job)}
        s=command(job,'state')['state'];session=context['session_id']
        # The append-only job is the current quota authority. A recorded human
        # amendment must not silently restore limits from the old CLI snapshot.
        args=SimpleNamespace(**{**vars(args),**{k:s['limits'][k] for k in ('budget_usd','max_steps','max_output')}})
        if (out/'metrics.json').exists() and (Path(cfg['state_root'])/'queue'/(session+'.json')).exists():return read(out/'metrics.json')
    else:
        cfg=load_config(args.rsi_config);provider=configured() if cfg['provider_mode']=='real' else None
        out=PRIVATE_HOME/'runs'/uuid4().hex;out.mkdir(parents=True,mode=0o700)
        env={'FM_TASK_FILE':os.environ['FM_TASK_FILE'],'FM_OUTPUT':os.environ['FM_OUTPUT'],'FM_JOB_FILE':str(out/'operation-job.json')};job=Path(env['FM_JOB_FILE'])
        limits={'budget_usd':args.budget_usd,'max_steps':args.max_steps,'max_output':args.max_output,'max_repairs':cfg['limits']['max_repairs']}
        s=initialize_job(job,Path(env['FM_TASK_FILE']),Path(env['FM_OUTPUT']),limits);session='sss-'+uuid4().hex
        context,_=enroll(args.rsi_config,prepared,session,out,args,env);origin=Path(context['origin'])
    if on_start:on_start(context)
    if not args.call_model:return {'paid':False,'original_job':str(job),'requests_used':s['requests'],'spent_usd':s['spent_units']/1e9,'limits':s['limits']}
    with writer_lock(out,'execution'):
        if s['accepted']:
            record=Path(cfg['state_root'])/'records'/(session+'.json')
            if record.exists():metrics=read(record)['metrics']
            elif (out/'metrics.json').exists():metrics=read(out/'metrics.json')
            else:
                ev=[json.loads(l) for l in (out/'agent-events.jsonl').read_text().splitlines()]
                metrics={'status':'done','session_id':session,'acceptance_passed':True,'acceptance_repairs':s['repairs'],'agent_steps':s['steps'],
                  'upstream_requests':s['requests'],'budget_accounted_usd':s['spent_units']/1e9,'original_job':str(job),'elapsed_seconds':None,
                  'attempt_files':[{'file':str(p),'sha256':sha(p),'attempt':p.parent.name} for p in (out/'attempts').glob('*/native-events.jsonl')],
                  'recovered_from_accepted_original_job':True,**_usage(ev)}
            value=seal(context,metrics);saved={**metrics,'continuous_rsi':value,'output_dir':str(out),'no_new_model_requests':True}
            if value['auto_worker']:saved['continuous_rsi']['worker']=launch_worker(args.rsi_config,cfg['state_root'])
            durable(out/'metrics.json',saved);return saved
        state=OperationBudget(job,out/'cost-ledger.jsonl');state.recover(s['execution_version_sha256'],os.getpid())
        attempt=out/'attempts'/uuid4().hex;attempt.mkdir(parents=True,mode=0o700)
        durable(attempt/'started.json',{'original_job':str(job),'source_sha256':context['source_sha256'],'pid':os.getpid()},exclusive=True)
        scene_patch=frozen_scene_patch(out,prepared,resume=bool(args.rsi_resume))
        rsi_patch=out/'rsi.patch.yml'
        operation_binding=out/'operation-binding.json'
        if args.rsi_resume and transition and transition['scope']=='reviewed_adapter_relocation':
            scene_patch=relocated_scene_patch(scene_patch,attempt)
            operation_binding=relocated_operation_binding(operation_binding,attempt,read(origin/'source-code.json'))
            rsi_patch=relocated_rsi_patch(rsi_patch,attempt,context['spec'].get('owner'))
        patches=[scene_patch,str(rsi_patch)]
        if args.rsi_resume:
            resume_patch=attempt/'native-resume.patch.yml'
            durable(resume_patch,[{'id':'sdk-jsonrpc-server','disabled':True},
                {'insert':[{'id':'file-native-resume-server','name':(ROOT/'src/adapters/harness/learning/dsh_file_resume.ts').as_uri(),
                'config':{'session_id':session}}]}],exclusive=True)
            patches.append(str(resume_patch))
        if prepared['acceptance_guard']['max_repairs']!=s['limits']['max_repairs']:
            policy=next(p['config'] for p in prepared['agent_plugins'] if p['id']=='sss-acceptance-guard')
            patch=attempt/'current-quota.patch.yml'
            durable(patch,[{'id':'sss-acceptance-guard','config':{**policy,'max_repairs':s['limits']['max_repairs']}}],exclusive=True)
            patches.append(str(patch))
        if os.environ.get('HARLESS_FILE_APPROVAL_HOME'):
            approval=out/'file-approval.patch.yml'
            durable(approval,[{'insert':[{'id':'file-native-approval','name':(ROOT/'src/adapters/file_management/file_approval_bridge.ts').as_uri()}]}])
            patches.append(str(approval))
            env['HARLESS_FILE_APPROVAL_HOME']=os.environ['HARLESS_FILE_APPROVAL_HOME']
        env.update(SSS_OPERATION_BINDING=str(operation_binding),SSS_EXPERIENCE_BINDING=str(out/'experience-binding.json'),
            SSS_CONTINUOUS_RSI_BINDING=str(out/'rsi-binding.json'),DSH_HOME=str(out/'dsh'),SSS_SCENARIO_PRESENTATION='native',SSS_SCENARIO_TOOLS=json.dumps(prepared['allowed_tools']))
        endpoint=model_api_root()
        if cfg['provider_mode']=='mock':
            import re
            endpoint=os.environ.get('SSS_MOCK_ENDPOINT','')
            if not re.fullmatch(r'http://127\.0\.0\.1:\d+',endpoint):raise ValueError('mock task requires an explicit local mock endpoint; no cloud fallback')
        from .management_platform_budget import enroll_platform
        platform=enroll_platform(session,args.model,args.budget_usd,out,resuming=bool(args.rsi_resume)) if cfg['provider_mode']=='real' else None
        if platform:endpoint=platform.upstream
        headers=platform_headers(platform.headers,provider) if provider and platform else platform.headers if platform else None
        gate=create_server('127.0.0.1',0,endpoint,state,forward_headers=headers,forward_model_alias=platform is None)
        if cfg['provider_mode'] == 'real' and platform is None:
            if provider:
                attach(gate, provider)
                env['DEEPSEEK_API_KEY'] = 'file-provider-host-credential'
            elif model_api_key_configured():
                env['DEEPSEEK_API_KEY'] = model_sdk_key()
        thread=threading.Thread(target=gate.serve_forever,daemon=True);thread.start()
        env.update(DEEPSEEK_BASE_URL=f'http://127.0.0.1:{gate.server_port}/v1',SSS_BUDGET_GATE_ACTIVE='1',SSS_BUDGET_CAP_USD='null' if args.budget_usd is None else str(args.budget_usd),SSS_BUDGET_LEDGER=str(state.record))
        prior=[json.loads(l) for l in (out/'agent-events.jsonl').read_text().splitlines()] if (out/'agent-events.jsonl').exists() else []
        count=len(prior);guard=NativeBudgetGuard(max_model_requests=None if s['limits']['max_steps'] is None else max(1,s['limits']['max_steps']-s['steps']),max_observed_input_tokens=None)
        def observe(n):
            nonlocal count
            event=None
            if n.method=='session.event' and isinstance(n.payload.get('event'),dict):
                e=n.payload['event']
                event=e
                with (attempt/'native-events.jsonl').open('a') as f:f.write(json.dumps(e,ensure_ascii=False)+'\n')
                count+=1;combined={**e,'seq':count,'original_seq':e['seq'],'durable_attempt':attempt.name}
                with (out/'agent-events.jsonl').open('a') as f:f.write(json.dumps(combined,ensure_ascii=False)+'\n')
                if mcp_transport_interrupted(e):raise RuntimeError('MCP transport interrupted; retain the original job for recovery')
            guard.on_notification(n)
            if on_event and event:on_event(event)
        start=time.monotonic();error=None
        try:
            max_tokens = args.max_output
            if max_tokens is None and cfg['provider_mode'] == 'real':
                max_tokens = next((route['max_output_tokens'] for route in model_routes()
                                   if route['id'] == args.model), None)
                if max_tokens is None and provider and args.model in provider['provider_binding']['model_map']:
                    max_tokens = 393216
            with create_harness(root=ROOT,patches=tuple(patches),env=env,provider='deepseek-official',model=args.model,max_tokens=max_tokens,
                                cwd=str(out),runtime_cwd=str(out),request_timeout_seconds=900) as h:
                prompt=('继续这同一个文件管理任务。沿用原目标、权限和已保存的工具结果；检查当前状态后续接尚未完成的工作，'
                        '不要重复已经成功的读取、判断或写入。' if args.rsi_resume else context['prompt'])
                result=h.run(prompt,session_id=session,on_notification=observe)
            (out/'answer.md').write_text(result.final_response)
        except (Exception, KeyboardInterrupt) as e:error={'type':type(e).__name__,'message':str(e)[:2000]}
        finally:gate.shutdown();gate.server_close();thread.join(timeout=5)
        s=command(job,'state')['state'];events=[json.loads(l) for l in (out/'agent-events.jsonl').read_text().splitlines()] if (out/'agent-events.jsonl').exists() else []
        attempts=[]
        for a in (out/'attempts').glob('*/native-events.jsonl'):attempts.append({'file':str(a),'sha256':sha(a),'attempt':a.parent.name})
        trace=PRIVATE_HOME/'task-acceptance'/hashlib.sha256(str(job.resolve()).encode()).hexdigest()
        checks=[read(p) for p in sorted(trace.glob('round-*/result.json'))]
        metrics={'status':'done' if s['accepted'] else 'interrupted' if s['status'] in ('running','paused') else s['status'],'output_dir':str(out),
          'session_id':session,'acceptance_passed':s['accepted'],'acceptance_repairs':s['repairs'],'agent_steps':s['steps'],
          'upstream_requests':state.request_count,'budget_accounted_usd':state.reserved_usd,'elapsed_seconds':round(time.monotonic()-start,3),
          'original_job':str(job),'attempt_files':attempts,'acceptance_checks':len(checks),'error':error,
          **({'provider_binding':provider['provider_binding']} if provider and cfg['provider_mode']=='real' else {}),**_usage(events)}
        if args.rsi_resume and transition:
            key='recovery_source_relocation' if transition['scope']=='reviewed_adapter_relocation' else 'recovery_observer_transition'
            metrics[key]=transition
        if platform:platform.close(metrics['status']=='interrupted')
        durable(attempt/'outcome.json',metrics,exclusive=True)
        if metrics['status']=='interrupted':
            if s['status']=='running':command(job,'pause')
            metrics['resume_origin']=str(origin);durable(out/'interrupted.json',metrics)
            return metrics
        durable(out/'metrics.json',metrics)
        metrics['continuous_rsi']=seal(context,metrics)
        if metrics['continuous_rsi']['auto_worker']:metrics['continuous_rsi']['worker']=launch_worker(args.rsi_config,cfg['state_root'])
        durable(out/'metrics.json',metrics);return metrics
