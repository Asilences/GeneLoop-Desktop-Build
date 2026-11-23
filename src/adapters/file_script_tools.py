"""File-source programs execute in the existing container, through current tool guards.

Source and actual child calls are durable evidence, never synthesized native events.
An unfinished invocation cannot be retried as a new effect. The ordinary Harness
receives its receipt and must inspect current state before repairing.
"""
from __future__ import annotations
import asyncio, copy, inspect, json, os, re
from pathlib import Path
from jsonschema import Draft202012Validator
from mcp.server.mcpserver.exceptions import ToolError
from src.motif_core.reuse.experience_registry import digest, durable, read, sha
from src.adapters.source_program_compiler import compile_source_program, PARAMETER_TOKEN

TOOLS = ['script_catalog', 'inspect_script_result', 'run_script']
FORMAT = 'sss-file-source-program-v1'
MAX_CALLS = 256


def contract(name):
    return {'format':'sss-mcp-learning-v1','effect':'semantic',
            'auto_continue':False,'exports':[],'statuses':['script_completed']}


def validate_source(source, parameters, description, schema):
    # compile_source_program also checks the actual raw-source SHA. Its helper
    # uses SHA256 of source bytes, whereas digest deliberately hashes JSON here.
    from src.motif_core.offline.compilation.script_motif_compiler import sha as source_sha
    return compile_source_program({'description':description,'language':'javascript','template':source,
        'parameters_schema':schema,'default_parameters':parameters},
        {'task_id':'file-source-admission','events_sha256':'pending-native-observation',
         'source':source,'source_sha256':source_sha(source)})


def checked_script_policy(policy):
    if (policy.get('format')!=FORMAT or policy.get('policy_digest')!=digest({k:v for k,v in policy.items() if k!='policy_digest'})
        or policy.get('artifact',{}).get('kind')!='learned_file_source_program'):
        raise ValueError('file script signature changed')
    a=policy['artifact']
    if a.get('certified_digest')!=digest({k:v for k,v in a.items() if k!='certified_digest'}):
        raise ValueError('file script artifact changed')
    validate_source(a['source'],a['example_parameters'],a['description'],a['parameters_schema'])
    return policy


class FileScripts:
    def script_delivery_state(self):
        """Host receipts, not model summaries. No parsing or file reads are repeated."""
        from management_reading import coverage
        return {'input_sha256':self.input_digest,'snapshot_sha256':digest(self.actual_tree()),
            'file_ids':list(self.files()),
            'documents':[{'path':d['anchor']['path'],**coverage(d)} for d in self.documents.values()],
            'report_required':True,
            'next_action':'Call submit_report(summary, gaps) before the final answer; OMIT file_ids to let the host bind all current permitted files. These IDs remain available for compatibility. inspect_script_result retrieves retained child evidence without repeating reads. Completion of a script is not submission of the task report.'}

    def inspect_script_result(self,execution_id:str,start:int=0,limit:int=20)->dict:
        """Inspect original script effects/results before ordinary repair or recovery.
        Pagination preserves full evidence; an unfinished call is never rerun here.
        """
        self.active()
        if (len(execution_id)!=64 or any(c not in '0123456789abcdef' for c in execution_id)
            or type(start) is not int or start<0 or type(limit) is not int or not 1<=limit<=40):raise ToolError('invalid script receipt page')
        directory=self.output/'script-runs'/execution_id
        if not (directory/'invocation.json').is_file():raise ToolError('unknown script execution')
        q=read(directory/'invocation.json')
        if q['task_sha256']!=self.input_digest:raise ToolError('foreign script receipt')
        calls=[read(p) for p in sorted(directory.glob('call-[0-9][0-9][0-9][0-9].json'))]
        receipt=read(directory/'receipt.json') if (directory/'receipt.json').exists() else None
        starts=[read(p) for p in sorted(directory.glob('call-*-start.json'))]
        finished={r['sequence'] for r in calls}
        return self.stamp({'execution_id':execution_id,'status':receipt['status'] if receipt else 'interrupted_or_running',
            'calls':calls[start:start+limit],'total_recorded_calls':len(calls),
            'next_start':start+limit if start+limit<len(calls) else None,
            'unknown_effect_calls':[r for r in starts if r['sequence'] not in finished],
            'receipt':receipt['public'] if receipt else None,'delivery_state':self.script_delivery_state(),
            'instruction':'Use current inventory and native plan receipts; do not repeat unknown effects.'})
    def _script_binding(self):
        from src.adapters.continuous_rsi import private
        path=self.output/'file-script-binding.json'
        if not path.exists():return None
        b=read(path)
        if b['task_sha256']!=self.input_digest:raise ToolError('script task grant changed')
        registry=private(b['registry_file'])
        if sha(registry)!=b['registry_sha256']:raise ToolError('script frozen library changed')
        return b

    def _scripts(self):
        from src.adapters.continuous_rsi import private
        from src.adapters.experience_library import policy_current
        from src.adapters.file_management.experience_certification import check_motif_certificate
        b=self._script_binding()
        if not b:return []
        registry=read(b['registry_file']);root=private(b['registry_root'])
        if registry['registry_digest']!=digest({k:v for k,v in registry.items() if k!='registry_digest'}):
            raise ToolError('script registry changed')
        entries=[]
        for e in registry['entries']:
            if e['kind']!='file_script' or e['state'] not in (['active','candidate'] if b['role']=='certify' else ['active']):continue
            try:
                path=private(root/e['payload'])
                if not path.is_relative_to(root) or sha(path)!=e['sha256']:raise ValueError('script source object changed')
                policy=checked_script_policy(read(path))
                if e.get('runtime_source')!=b['runtime_source']:raise ValueError('script implementation closure changed; independent recertification required')
                if not policy_current(policy,b['runtime_source']):raise ValueError('script runtime/tool contract changed; ordinary fallback')
                if e['state']=='active':
                    cert=private(root/e['certificate']['file'])
                    if not cert.is_relative_to(root) or sha(cert)!=e['certificate']['sha256']:raise ValueError('script certificate changed')
                    check_motif_certificate(policy,cert,e['sha256'])
                entries.append((e,policy))
            except (ValueError,KeyError,TypeError,OSError) as error:
                rejection={'entry_id':e['entry_id'],'reason':str(error),'registry_sha256':b['registry_sha256']}
                receipt=self.output/'script-rejections'/(digest(rejection)+'.json')
                if not receipt.exists():
                    durable(receipt,rejection,exclusive=True)
                    with Path(b['audit_file']).open('a',encoding='utf-8') as stream:
                        stream.write(json.dumps({'kind':'experience_deferred',**rejection,'executed':False},ensure_ascii=False)+'\n')
        return entries

    def script_catalog(self, query:str='', start:int=0, limit:int=10)->dict:
        """Find certified parameterized File scripts. Matching is not permission.
        Pass the selected script_id and CURRENT parameters to run_script; examples
        describe interfaces, never the current file identities or expected answer.
        """
        self.active();rows=[]
        if type(start) is not int or start<0 or type(limit) is not int or not 1<=limit<=20:raise ToolError('invalid script catalog page')
        terms=set(re.findall(r'\w+',query.casefold()))
        for e,p in self._scripts():
            a=p['artifact']
            rows.append({'script_id':e['entry_id'],'description':a['description'],
                'parameters_schema':a['parameters_schema'],'source_kind':a['source_kind'],
                'generation':e.get('activated_generation'),'source_sha256':digest(a['source']),
                'lexical_overlap':len(terms & set(re.findall(r'\w+',a['description'].casefold())))})
        rows.sort(key=lambda r:(-r['lexical_overlap'],r['script_id']))
        return self.stamp({'scripts':rows[start:start+limit],'total':len(rows),
            'next_start':start+limit if start+limit<len(rows) else None,
            'selection':'ranked lexical hints only; model checks current goal, parameters and tool contracts; no task-number routing',
            'unmatched_candidates_retained':True})

    async def run_script(self, parameters:dict, script_id:str='', source:str='', description:str='', parameters_schema:dict|None=None)->dict:
        """Execute a learned script OR ordinary model-authored JavaScript safely.
        New source needs description, object parameters_schema and exactly one
        __GENELOOP_PARAMETERS__ token, e.g. const p=__GENELOOP_PARAMETERS__;
        await files.call({name:'list_files',arguments:{}}). Calls use the SAME
        allowed File tools, permissions, journals and current bytes. console.log
        returns results. Reuse supplies script_id + current parameters only.
        delivery_state returns actual coverage and current file_ids for submit_report;
        inspect_script_result retrieves child evidence without rereading documents.
        files.call returns the tool's direct result object: pin_files returns
        parallel file_ids/source_ids arrays; open_document returns request_id;
        read_document_chunk returns text and next_request_id (null at end);
        document_coverage returns complete, delivered_characters, completed_pages.
        Call submit_report before your final answer; script completion is not delivery.
        read_task must precede this call. No network or host filesystem is exposed.
        Partial/unknown effects require ordinary state inspection, never blind retry.
        """
        self.active()
        if script_id:
            if source or description or parameters_schema:raise ToolError('learned identity and new source cannot be mixed')
            entry,policy=next(((e,p) for e,p in self._scripts() if e['entry_id']==script_id),(None,None))
            if not policy:raise ToolError('script missing, disabled or incompatible; use ordinary tools')
            a=policy['artifact'];source=a['source'];description=a['description'];parameters_schema=a['parameters_schema']
        else:entry=policy=None
        try:validate_source(source,parameters,description,parameters_schema or {})
        except Exception as error:raise ToolError('script source/parameter admission: '+str(error)) from error
        if len(json.dumps(parameters,ensure_ascii=False).encode())>32000:raise ToolError('script parameters too large')
        code=source.replace(PARAMETER_TOKEN,json.dumps(parameters,ensure_ascii=False,separators=(',',':')))
        invocation=digest({'task':self.input_digest,'source':source,'parameters':parameters,'script_id':script_id})
        directory=self.output/'script-runs'/invocation;receipt=directory/'receipt.json'
        if directory.exists():
            if receipt.exists():
                old=read(receipt)
                if old['status']=='script_completed' and self.actual_tree()==old['after']:
                    return self.stamp({**old['public'],'replayed_receipt':True})
            raise ToolError('original script partial, failed or state changed; inspect script receipt '+invocation+' and current journals before ordinary repair')
        directory.mkdir(parents=True,mode=0o700)
        frozen={'format':'sss-file-script-invocation-v1','execution_id':invocation,'task_sha256':self.input_digest,
            'source':source,'parameters':copy.deepcopy(parameters),'parameters_schema':parameters_schema,
            'description':description,'script_id':script_id,'before':copy.deepcopy(self.actual_tree()),
            'source_kind':'certified_reuse' if script_id else 'native_source','runtime_version':self.execution_version}
        durable(directory/'invocation.json',frozen,exclusive=True)
        binding=self._script_binding()
        if binding and script_id:
            with Path(binding['audit_file']).open('a',encoding='utf-8') as stream:
                stream.write(json.dumps({'kind':'experience_selected','entry_id':script_id,'experience_kind':'file_script',
                    'activated_generation':entry.get('activated_generation'),'execution_id':invocation})+'\n')
        from management_tools import TOOLS as all_tools, ROOT
        allowed=set(all_tools)-{'read_task','run_script','script_catalog','inspect_script_result','submit_report','view_document_page'}
        calls=[];child=None;result=None;failed=None
        try:
            child=await asyncio.create_subprocess_exec('node','--experimental-strip-types',str(ROOT/'src/adapters/file_script_runtime.ts'),
                stdin=asyncio.subprocess.PIPE,stdout=asyncio.subprocess.PIPE,stderr=asyncio.subprocess.PIPE,
                limit=5*1024*1024,env={'PATH':os.environ.get('PATH','/usr/bin:/bin:/opt/homebrew/bin'),'LANG':'en_US.UTF-8'})
            child.stdin.write((json.dumps({'type':'run','program':code})+'\n').encode());await child.stdin.drain()
            while True:
                raw=await asyncio.wait_for(child.stdout.readline(),timeout=80)
                if not raw:raise ValueError('script worker exited before receipt')
                row=json.loads(raw)
                if row.get('type')=='done':result=row['result'];break
                if (row.get('type')!='call' or row.get('id')!=len(calls)+1 or row.get('name') not in allowed
                    or not isinstance(row.get('arguments'),dict) or len(calls)>=MAX_CALLS):raise ValueError('script dispatch outside bounded File tools')
                self.active();call={'sequence':row['id'],'name':row['name'],'arguments':row['arguments']}
                durable(directory/(f'call-{row["id"]:04d}-start.json'),call,exclusive=True)
                response={'type':'response','id':row['id']}
                try:
                    value=getattr(self,row['name'])(**row['arguments'])
                    if inspect.isawaitable(value):value=await value
                    if row['name']=='execute_tool_call' and value.get('status')=='completed':
                        observed=self.gateway().inspect_tool_result(value['receipt_id'])
                        raw=observed.get('actual_mcp_result',{});data=raw.get('structuredContent',raw.get('structured_content',{}))
                        if not data:
                            for item in raw.get('content',[]):
                                if item.get('type')=='text':
                                    try:data=json.loads(item['text'])
                                    except (ValueError,KeyError):continue
                                    break
                        if raw.get('isError') or isinstance(data,dict) and (data.get('status')=='execution_failed' or data.get('result',{}).get('error')):
                            raise ValueError('provider returned an internal execution error; completion is not success')
                    call['out']=value;response['value']=value
                except Exception as error:
                    call['error']=type(error).__name__+': '+str(error);response['error']=call['error']
                calls.append(call);durable(directory/(f'call-{row["id"]:04d}.json'),call,exclusive=True)
                child.stdin.write((json.dumps(response,ensure_ascii=False)+'\n').encode());await child.stdin.drain()
            if result.get('error') or any('error' in c for c in calls):failed='script or tool failure; ordinary inspection required'
        except (Exception,asyncio.CancelledError) as error:
            failed=type(error).__name__+': '+str(error)
            if isinstance(error,asyncio.CancelledError):failed='cancelled; original effects retained'
        finally:
            if child:
                if child.returncode is None:
                    try:await asyncio.wait_for(child.wait(),timeout=3)
                    except asyncio.TimeoutError:child.terminate();await child.wait()
                stderr=(await child.stderr.read()).decode(errors='replace')
                if stderr:(directory/'worker-stderr.txt').write_text(stderr,encoding='utf-8')
        after=self.actual_tree();public={'status':'script_failed' if failed else 'script_completed','execution_id':invocation,
            'script_id':script_id or None,'source_sha256':digest(source),'actual_tool_calls':len(calls),
            'result':result,'error':failed,'original_effects_preserved':True,'receipt':str(receipt),
            'delivery_state':self.script_delivery_state()}
        durable(receipt,{'format':'sss-file-script-receipt-v1','status':public['status'],'invocation_sha256':sha(directory/'invocation.json'),
            'calls_sha256':digest(calls),'before':frozen['before'],'after':after,'public':public},exclusive=True)
        b=self._script_binding()
        if b:
            with Path(b['audit_file']).open('a',encoding='utf-8') as stream:
                stream.write(json.dumps({'kind':'file_script_complete' if not failed else 'file_script_failed',
                    'entry_id':script_id or None,'execution_id':invocation,'receipt_sha256':sha(receipt),
                    'actual_tool_calls':len(calls),'source_kind':frozen['source_kind']},ensure_ascii=False)+'\n')
                if failed and script_id:
                    stream.write(json.dumps({'kind':'experience_deferred','entry_id':script_id,'reason':failed,
                        'original_effects_preserved':True,'execution_id':invocation},ensure_ascii=False)+'\n')
        return self.stamp(public)


def script_observations(spec,delivery,rows):
    """Expand verified child receipts for replay, while preserving their provenance."""
    delivery=Path(delivery);expanded=[]
    for parent in rows:
        if not parent.get('out') or not parent['name'].endswith('__run_script'):continue
        out=parent['out'];key=out.get('execution_id','')
        if len(key)!=64 or any(c not in '0123456789abcdef' for c in key):raise ValueError('invalid actual script receipt')
        directory=delivery/'script-runs'/key;receipt=read(directory/'receipt.json');q=read(directory/'invocation.json')
        if (receipt['invocation_sha256']!=sha(directory/'invocation.json') or q['task_sha256']!=digest(spec)
            or q['execution_id']!=key or receipt['public']!={k:v for k,v in out.items() if k not in ('_sss_scope','_sss_authorized','replayed_receipt')}):
            raise ValueError('script receipt differs from actual parent result')
        args=parent['args']
        if args.get('parameters')!=q['parameters'] or args.get('script_id','')!=q['script_id']:
            raise ValueError('script actual parameter binding differs')
        if not q['script_id'] and any(args.get(k)!=q[k] for k in ('source','description','parameters_schema')):
            raise ValueError('script source differs from native call')
        calls=[read(p) for p in sorted(directory.glob('call-[0-9][0-9][0-9][0-9].json'))]
        if digest(calls)!=receipt['calls_sha256'] or [c['sequence'] for c in calls]!=list(range(1,len(calls)+1)):
            raise ValueError('script actual call evidence changed')
        for call in calls:
            if call.get('error'):continue
            expanded.append({'name':'mcp__file_management__'+call['name'],'args':call['arguments'],'out':call['out'],
                'call_id':key+':'+str(call['sequence']),'call_seq':parent['call_seq'],'result_seq':parent['result_seq'],
                'generated':True,'message_seq':None,'script_parent_call_id':parent['call_id']})
    return expanded
