"""Learn File source from actual ordinary programs and witnessed tool dataflow.

Discovery never executes code. Admission uses the original worker, real-model
native certification and two actual candidate executions on separate material.
"""
from __future__ import annotations
import copy,json
from pathlib import Path
from src.motif_core.reuse.experience_registry import digest,read,sha,durable,ExperienceRegistry
from .file_script_tools import FORMAT,validate_source,checked_script_policy,script_observations


def identity(compiled):
    return digest({k:compiled[k] for k in ('source','parameters_schema')})


def fresh_read_material(spec, work, nonce, variant=None):
    """Counterfactual body fixtures for mechanical full-read scripts, not semantic tasks.

    Entire text bodies change. In particular a PDF metadata nonce is NOT enough
    to certify a source program against memorized content. Other task kinds keep
    their existing material adapter and are reported with that narrower scope.
    """
    quality=spec.get('quality',{});requirements=quality.get('requirements',[])
    contract=quality.get('delivery_contract',{})
    mechanical_contract=(contract.get('format')=='sss-file-delivery-v1' and contract.get('require_reads')
        and contract.get('preserve_originals') is True and contract.get('exact_tree') is True
        and all(r.get('mode') in (None,'text') for r in contract['require_reads'])
        and not set(contract)-{'format','require_reads','preserve_originals','exact_tree','search_queries'})
    if not spec.get('rules',{}).get('read_only') or not (requirements or mechanical_contract):return False
    if any(r.get('kind') not in ('read','unchanged') for r in requirements):return False
    import csv,io,random
    rng=random.Random(nonce)
    for path in sorted(Path(work).rglob('*')):
        if not path.is_file() or path.name=='.experiment-copy':continue
        ext=path.suffix.lower();text='Fresh independent body '+nonce+' '+path.name+'\n'
        text+='\n'.join('Record '+str(i)+': measured value '+str(rng.randint(1,999999))+'; limitation and appendix.' for i in range(17))
        if ext in ('.txt','.md'):path.write_text(text,encoding='utf-8')
        elif ext in ('.csv','.tsv'):
            buffer=io.StringIO();writer=csv.writer(buffer,delimiter='\t' if ext=='.tsv' else ',');writer.writerow(['item','value','evidence'])
            for i in range(11):writer.writerow([nonce[:8]+'-'+str(i),rng.randint(1,9999),'independent body'])
            path.write_text(buffer.getvalue(),encoding='utf-8')
        elif ext=='.pdf':
            import pymupdf
            with pymupdf.open(path) as old:count=len(old)
            if variant is not None:count=3 if variant=='native-cert' else 5 if variant=='execute-cert-0' else count+1
            doc=pymupdf.open()
            for i in range(count):
                page=doc.new_page();page.insert_textbox(pymupdf.Rect(30,30,560,810),'Physical page '+str(i+1)+'\n'+text,fontsize=10)
            data=doc.tobytes();doc.close();path.write_bytes(data)
        elif ext=='.docx':
            from docx import Document
            document=Document();document.add_heading('Independent current material',0)
            for line in text.splitlines():document.add_paragraph(line)
            document.save(path)
        elif ext=='.xlsx':
            from openpyxl import Workbook
            book=Workbook();book.active.append(['item','value','evidence'])
            for i in range(11):book.active.append([i,rng.randint(1,9999),nonce])
            book.save(path)
        elif ext in ('.png','.jpg','.jpeg'):
            from PIL import Image,ImageDraw
            image=Image.new('RGB',(1200,500),'white');draw=ImageDraw.Draw(image)
            draw.text((30,30),'Independent material '+nonce+'\nCurrent value '+str(rng.randint(1,9999)),fill='black');image.save(path)
        elif ext=='.json':path.write_text(json.dumps({'independent':nonce,'values':[rng.randint(1,9999) for _ in range(11)]}),encoding='utf-8')
        else:raise ValueError('no fresh-body script certification adapter for '+ext)
    if mechanical_contract and variant is not None:
        # The goal remains "all current documents". Both names and cardinality
        # change before this material and its acceptance predicates are frozen.
        extra=0 if variant=='native-cert' else 1 if variant=='execute-cert-0' else 2
        for i in range(extra):
            (Path(work)/('independent-extra-'+str(i)+'.csv')).write_text('record,value\n'+nonce+','+str(i)+'\n')
        for i,path in enumerate(sorted(Path(work).rglob('*'))):
            if path.is_file() and path.name!='.experiment-copy':path.rename(path.with_name('independent-'+nonce[:12]+'-'+str(i)+path.suffix.lower()))
        default_mode=None if all(r.get('mode') is None for r in contract['require_reads']) else 'text'
        contract['require_reads']=[{'path':p.relative_to(work).as_posix(),**({'mode':default_mode} if default_mode else {})}
            for p in sorted(Path(work).rglob('*')) if p.is_file() and p.name!='.experiment-copy']
        quality['goal']['delivery_contract_sha256']=digest(contract)
    return True


def graph_source(compiled, tools):
    """Mechanically compile observed bindings/branches, not a hand-authored task route."""
    nodes=compiled['nodes'];root=compiled.get('root',nodes[0]['tool'])
    schema=tools[root]['schema'];names=[n['tool'] for n in nodes]
    helper='''const p=__GENELOOP_PARAMETERS__;
function at(value,path){const parts=path.split('.');const head=parts.shift();if(head.endsWith('[]'))return value[head.slice(0,-2)].map(x=>parts.length?at(x,parts.join('.')):x);const next=value[head];return parts.length?at(next,parts.join('.')):next;}
const evidence=[];
'''
    if compiled.get('kind')=='learned_mcp_control_flow':
        source=helper+'const edges='+json.dumps(compiled['edges'],separators=(',',':'))+';\n'
        source+='let tool='+json.dumps(root)+',args=p,done=false;\n'
        source+='''for(let step=0;step<256;step++){
 const value=await files.call({name:tool.replace('mcp__file_management__',''),arguments:args});
 evidence.push({tool,result:value});
 const matches=edges.filter(e=>e.from===tool&&Object.entries(e.guard).every(([k,v])=>v==='present'?value[k]!==null&&value[k]!==undefined:v==='null'?value[k]===null:value[k]===v));
 if(matches.length!==1)throw Error('observed control-flow guard is not uniquely satisfied');
 const edge=matches[0];if(edge.to===null){done=true;break;}
 args=Object.fromEntries(Object.entries(edge.bindings).map(([k,v])=>[k,at(value,v)]));tool=edge.to;
}
if(!done)throw Error('bounded script incomplete; continue with ordinary tools');
console.log(JSON.stringify(evidence));'''
    else:
        source=helper+'const nodes='+json.dumps(nodes,separators=(',',':'))+';\n'
        source+='''for(let i=0;i<nodes.length;i++){
 const node=nodes[i];const args=i===0?p:Object.fromEntries(Object.entries(node.bindings).map(([k,b])=>[k,at(evidence[b.node].result,b.path)]));
 const result=await files.call({name:node.tool.replace('mcp__file_management__',''),arguments:args});evidence.push({tool:node.tool,result});
}
console.log(JSON.stringify(evidence));'''
    return {'source':source,'parameters_schema':schema,
        'description':'Execute witnessed File dataflow on current parameters: '+' → '.join(n.replace('mcp__file_management__','') for n in names),
        'source_kind':'compiled_tool_trace'}


def discover_scripts(frames, graph_candidates):
    groups={};excluded=[]
    for f in frames:
        # Existing workspace-runtime source is also real source evidence. A
        # wrapper reuses the SAME code worker and replaces only observed path
        # literals; unsupported literal forms are rejected, never guessed.
        for row in f['rows']:
            if row.get('generated') or not row['name'].endswith('__prepare_tool_call') or not row.get('out'):continue
            args=row['args']
            if args.get('provider_id')!='workspace-runtime' or args.get('tool_name')!='execute_code':continue
            try:
                program=args['arguments']['program'];rid=row['out']['request_id']
                executed=next(r for r in f['rows'] if r['name'].endswith('__execute_tool_call') and r['args'].get('request_id')==rid and r.get('out',{}).get('status')=='completed')
                inspected=next(r for r in f['rows'] if r['name'].endswith('__inspect_tool_result') and r['args'].get('receipt_id')==executed['out']['receipt_id'] and r.get('out'))
                raw=inspected['out']['actual_mcp_result'];data=raw.get('structuredContent',raw.get('structured_content',{}))
                if not data:
                    data=next(json.loads(v['text']) for v in raw.get('content',[]) if v.get('type')=='text')
                if data.get('status')!='completed' or data.get('result',{}).get('error'):raise ValueError('raw code did not actually succeed')
                slots={};substitutions=[]
                names=list(f['spec']['initial_tree']['workspace']['files'])+[v['name'] for v in data.get('artifacts',[])]
                for name in dict.fromkeys(names):
                    if name=='.experiment-copy' or name not in program:continue
                    literals=[quoted for quoted in (json.dumps(name,ensure_ascii=False),repr(name)) if quoted in program]
                    if not literals:raise ValueError('raw code input path is not an exact replaceable literal')
                    slot='path_'+str(len(slots));slots[slot]=name
                    for literal in literals:substitutions.append((literal,slot))
                source='const p=__GENELOOP_PARAMETERS__;let program='+json.dumps(program,ensure_ascii=False)+';\n'
                for literal,slot in substitutions:
                    source+='program=program.split('+json.dumps(literal,ensure_ascii=False)+').join(JSON.stringify(p['+json.dumps(slot)+']));\n'
                source+='''const q=await files.call({name:'prepare_tool_call',arguments:{provider_id:'workspace-runtime',tool_name:'execute_code',arguments:{program}}});
const r=await files.call({name:'execute_tool_call',arguments:{request_id:q.request_id}});
const out=await files.call({name:'inspect_tool_result',arguments:{receipt_id:r.receipt_id}});console.log(JSON.stringify(out));'''
                schema={'type':'object','properties':{k:{'type':'string','minLength':1,'description':'Current approved relative path replacing '+v} for k,v in slots.items()},
                    'required':list(slots),'additionalProperties':False}
                c={'source':source,'parameters_schema':schema,'description':('Reuse actually executed isolated code for: '+f['spec']['objective'])[:600],
                    'source_kind':'native_source','raw_source_sha256':digest(program),'original_tool':'workspace-runtime.execute_code',
                    'objective_sha256':digest(f['spec']['objective']),'source_execution_version':f['scope']['execution_version'],
                    'parent_policy_digests':sorted({r['entry_id'] for r in f.get('record',{}).get('selected',[])})}
                validate_source(source,slots,c['description'],schema);key=identity(c)
                g=groups.setdefault(key,{'compiled':c,'frames':[],'examples':[]})
                if f['fingerprint'] not in {v['fingerprint'] for v in g['frames']}:g['frames'].append(f);g['examples'].append(slots)
            except (ValueError,KeyError,StopIteration,TypeError) as error:
                excluded.append({'session_id':f['trace_id'],'reason':'raw executed source: '+str(error)})
        for row in f['rows']:
            if row.get('generated') or not row['name'].endswith('__run_script') or not row.get('out'):continue
            args=row['args'];out=row['out']
            if out.get('status')!='script_completed' or not args.get('source') or args.get('script_id'):continue
            try:
                children=[r for r in f['rows'] if r.get('script_parent_call_id')==row['call_id']]
                if not children and f.get('record',{}).get('delivery') and out.get('execution_id'):
                    children=script_observations(f['spec'],f['record']['delivery'],[row])
                terminal=('__read_file','__read_files','__read_document_chunk','__build_index','__search_index','__execute_plan','__restore_plan','__execute_tool_call')
                if children and not any(r['name'].endswith(terminal) for r in children):
                    raise ValueError('source performs setup only; no observed reading, processing or file effect')
                source=args['source'];schema=args['parameters_schema'];params=args['parameters']
                validate_source(source,params,args['description'],schema)
                # Current input identities belong in parameters, not frozen code.
                for name in f['spec']['initial_tree']['workspace']['files']:
                    if name=='.experiment-copy':continue
                    if json.dumps(name) in source or repr(name) in source:raise ValueError('native source freezes a training path')
                c={'source':source,'parameters_schema':schema,'description':args['description'],'source_kind':'native_source',
                   'objective_sha256':digest(f['spec']['objective']),'source_execution_version':f['scope']['execution_version'],
                   'parent_policy_digests':sorted({r['entry_id'] for r in f.get('record',{}).get('selected',[])})}
                c['observed_completed_documents']=sum(bool(d.get('complete')) for d in out.get('delivery_state',{}).get('documents',[]))
                c['observed_tool_calls']=len(children)
                c['observed_terminal_tools']=sorted({r['name'].rsplit('__',1)[-1] for r in children if r['name'].endswith(terminal)})
                key=identity(c);g=groups.setdefault(key,{'compiled':c,'frames':[],'examples':[]})
                if f['fingerprint'] not in {v['fingerprint'] for v in g['frames']}:
                    g['frames'].append(f);g['examples'].append(params)
            except (ValueError,KeyError,TypeError) as error:excluded.append({'session_id':f['trace_id'],'reason':'source script: '+str(error)})
    candidates=[]
    for key,g in groups.items():
        # A literal executable source already supplies an implementation. One
        # actual ordinary execution can propose it; three NEW certification
        # executions must still prove current parameters and effects. Graph
        # induction continues to require its original two native decisions.
        if not g['frames']:continue
        candidates.append({'kind':'file_script','key':key,**g,'compiled':{**g['compiled'],'example_parameters':g['examples'][0]}})
    for graph in graph_candidates:
        if graph['kind']!='operation_graph':continue
        c=graph['compiled'];f=graph['frames'][0]
        # Existing script call boundaries cannot train a recursive fake witness.
        if any(n['tool'].endswith(('__run_script','__script_catalog','__inspect_script_result','__submit_report')) for n in c['nodes']):continue
        try:
            compiled=graph_source(c,f['tools']);compiled['source_execution_version']=f['scope']['execution_version'];root=c.get('root',c['nodes'][0]['tool'])
            params=next(r['args'] for r in f['rows'] if r['name']==root and not r.get('generated') and r.get('out'))
            compiled['example_parameters']=params;compiled['objective_sha256']=digest(f['spec']['objective'])
            validate_source(compiled['source'],params,compiled['description'],compiled['parameters_schema'])
            candidates.append({'kind':'file_script','key':identity(compiled),'compiled':compiled,'frames':graph['frames'],'graph_witness':graph})
        except (ValueError,KeyError,StopIteration,TypeError) as error:
            excluded.append({'opportunity_key':graph['key'],'reason':'tool program: '+str(error)})
    # One identity may have both kinds of source evidence. Preserve one job.
    unique={}
    for c in candidates:unique.setdefault(c['key'],c)
    return list(unique.values()),excluded


def recertification_candidates(root,frames,current):
    """Reuse old proved source as a candidate, never re-sign it as current proof."""
    from .experience_library import policy_current,sources
    if not (Path(root)/'registry/current.json').exists():return []
    registry=ExperienceRegistry(Path(root)/'registry');state=registry.load();known={c['key'] for c in current};out=[]
    for entry in state['entries']:
        if entry['kind']!='file_script':continue
        try:
            policy=checked_script_policy(read(registry.root/entry['payload']))
            if entry.get('runtime_source')==sources() and policy_current(policy,sources()):continue
            certificate=registry.root/entry['certificate']['file']
            if sha(certificate)!=entry['certificate']['sha256']:continue
            verify_script_certificate(policy,certificate,entry['sha256'])
            a=policy['artifact'];matches=[f for f in frames if digest(f['spec']['objective'])==a.get('objective_sha256')]
            if not matches:continue
            c={k:a[k] for k in ('source','parameters_schema','description','source_kind','example_parameters','objective_sha256')}
            c['historical_source']={'policy_digest':policy['policy_digest'],'payload_sha256':entry['sha256'],
                'certificate_sha256':entry['certificate']['sha256']}
            key=identity(c)
            if key in known:continue
            out.append({'kind':'file_script','key':key,'compiled':c,'frames':matches[:2]});known.add(key)
        except (ValueError,KeyError,TypeError,OSError):continue
    return out


def complete_script_execution(policy, record, audit):
    matches=[r for r in audit if r['kind']=='file_script_complete' and r.get('entry_id')==policy['policy_digest']]
    if len(matches)!=1 or not matches[0]['actual_tool_calls']:return False
    directory=Path(record['delivery'])/'script-runs'/matches[0]['execution_id']
    if sha(directory/'receipt.json')!=matches[0]['receipt_sha256']:return False
    receipt=read(directory/'receipt.json');q=read(directory/'invocation.json')
    calls=[read(p) for p in directory.glob('call-[0-9][0-9][0-9][0-9].json')]
    expected=set(policy['artifact'].get('observed_terminal_tools',[]))
    if expected and not expected<={r['name'] for r in calls if not r.get('error')}:return False
    return (receipt['status']=='script_completed' and receipt['invocation_sha256']==sha(directory/'invocation.json')
            and q['source']==policy['artifact']['source'] and q['script_id']==policy['policy_digest']
            and q['parameters_schema']==policy['artifact']['parameters_schema'])


def verify_script_certificate(policy,path,raw_sha):
    checked_script_policy(policy);cert=read(path)
    bounded=cert.get('status')=='certified_file_script_v4'
    if (cert.get('status') not in ('certified_file_script_v1','certified_file_script_v2','certified_file_script_v3','certified_file_script_v4') or cert.get('holdout_used') is not False
        or cert.get('quality_and_permission_required') is not True or cert.get('policy_digest')!=policy['policy_digest']
        or cert.get('payload_sha256')!=raw_sha or sha(cert['candidate_lock_file'])!=cert['candidate_lock_sha256']):
        raise ValueError('File source needs immutable independent certification')
    training=set(policy['artifact']['source_task_fingerprints']);reviews=[cert['native_review'],*cert['reviews']]
    if len(reviews)!=3 or len({r['task_fingerprint'] for r in reviews})!=3:raise ValueError('new native and two actual script materials required')
    sizes=[]
    for review in reviews:
        if review['task_fingerprint'] in training or sha(review['record_file'])!=review['record_sha256']:raise ValueError('script certification overlap or mutation')
        record=read(review['record_file'])
        if (record['role']!=review['role'] or record['provider_mode']!='real' or not record['accepted']
            or not record['lifecycle_verified'] or not bounded and not record['observed_usage_complete'] or record['metrics'].get('acceptance_repairs')):
            raise ValueError('script certification failed, repaired or unmetered')
        if bounded:
            from .file_cost_evidence import POLICY,record_evidence
            if cert.get('accounting_policy')!=POLICY or review.get('cost_evidence')!=record_evidence(record,POLICY):
                raise ValueError('bounded certificate lacks immutable reconciled cost evidence')
        if cert['status'] in ('certified_file_script_v2','certified_file_script_v3','certified_file_script_v4'):
            scope=read(review['material_scope_file'])
            if sha(review['material_scope_file'])!=review['material_scope_sha256'] or scope.get('format')!='sss-file-script-material-v2':
                raise ValueError('new script material proof changed')
            spec=read(Path(record['origin'])/'task.json')
            paths=set(spec['initial_snapshot'])-{'.experiment-copy'}
            if paths!=set(scope['input_paths']):raise ValueError('certification input roster differs')
            if scope['fresh_entire_bodies']:
                hashes={h for n,h in spec['initial_snapshot'].items() if n!='.experiment-copy'}
                if hashes & set(policy['artifact']['source_input_hashes']):raise ValueError('fresh source certification reuses a training body')
                if scope['binding_scope']=='all_current_inputs':
                    if paths & set(policy['artifact']['source_input_paths']):raise ValueError('fresh all-input certification reuses a training path')
                    sizes.append(len(paths))
        if review['role']=='candidate_certification':
            audit=Path(record['run_dir'])/'experience-audit.jsonl'
            if sha(audit)!=review['audit_sha256'] or not complete_script_execution(policy,record,[json.loads(l) for l in audit.read_text().splitlines()]):
                raise ValueError('no complete actual script reuse evidence')
            if cert['status'] in ('certified_file_script_v3','certified_file_script_v4'):
                proof=Path(review['output_review_file']);value=read(proof)
                if (sha(proof)!=review['output_review_sha256'] or value.get('format')!='sss-file-script-output-review-v2'
                        or value.get('passed') is not True or value.get('parent_session_id')!=record['session_id']
                        or not bounded and value.get('observed_usage_complete') is not True or value.get('error') or value.get('mechanical_errors')
                        or value.get('verdict',{}).get('passed') is not True or value.get('verdict',{}).get('critical_errors')):
                    raise ValueError('script lacks a successful independent local-output review')
                if bounded:
                    from .file_cost_evidence import ledger_evidence
                    expected=ledger_evidence(proof.parent/'http-ledger.jsonl',value['upstream_requests'],value['cost_usd'],value['observed_usage_complete'],cert['accounting_policy'])
                    if value.get('cost_evidence')!=expected:raise ValueError('output review cost proof changed')
    if sizes and len(set(sizes))!=3:raise ValueError('mechanical script needs three independently varied input counts')
    return cert


def certify_script(cfg,root,job,candidate):
    from .continuous_motif_learning import frame,run_material,state_event,script_output_review,SCRIPT_OUTPUT_REVIEW
    from .continuous_rsi import source_map
    from .experience_library import sources
    from .file_cost_evidence import POLICY,record_evidence
    bounded=cfg.get('accounting_policy')==POLICY
    lock=read(job/'candidate-lock.json')
    if lock['source_code']!=source_map() or lock['candidate_sha256']!=sha(job/'compiled.json'):raise ValueError('frozen script/source changed')
    frames=[frame(read(t['record_file'])) for t in lock['training']]
    if any(sha(t['record_file'])!=t['record_sha256'] or t['task_fingerprint']!=f['fingerprint'] for t,f in zip(lock['training'],frames)):
        raise ValueError('script training evidence changed')
    compiled=read(job/'compiled.json')
    if compiled.get('output_review_contract')!=SCRIPT_OUTPUT_REVIEW:raise ValueError('new script certification requires mandatory current local-output review')
    registry=ExperienceRegistry(root/'registry');runtime=sources()
    native_file=job/'native-review.json';policy_file=job/'policy.json'
    if not policy_file.exists():
        empty=job/'empty-registry.json'
        if not empty.exists():
            value={'schema_version':1,'format':'sss-experience-registry-v1','generation':0,'parent_digest':None,'entries':[],
                'automatic_selection_uses_profile_id':False,'reason':'independent native script reference'}
            value['registry_digest']=digest(value);durable(empty,value,exclusive=True)
        native=run_material(cfg,job,'native-cert',frames[0]['record'],'native_certification',empty);nf=frame(native)
        artifact={**compiled,'kind':'learned_file_source_program','status':'trace_validated_effectful',
            'source_task_fingerprints':[f['fingerprint'] for f in frames], 'validation_task_fingerprint':nf['fingerprint'],
            'certification_contract':'sss-file-source-certification-v4' if bounded else 'sss-file-source-certification-v3','tool_contracts':nf['tools'],
            'source_input_paths':sorted({n for f in frames for n in f['spec']['initial_snapshot'] if n!='.experiment-copy'}),
            'source_input_hashes':sorted({h for f in frames for n,h in f['spec']['initial_snapshot'].items() if n!='.experiment-copy'}),
            'proposal_analysis_compatibility':[f.get('proposal_analysis_compatibility') for f in frames]}
        artifact['certified_digest']=digest(artifact)
        policy={'schema_version':1,'format':FORMAT,'execution_version_sha256':nf['scope']['execution_version'],'artifact':artifact}
        policy['policy_digest']=digest(policy)
        file=root/'records'/(native['session_id']+'.json')
        scope_file=job/'materials/native-cert/script-material-scope.json'
        durable(native_file,{'role':'native_certification','task_fingerprint':native['task_fingerprint'],
            'material_scope_file':str(scope_file),'material_scope_sha256':sha(scope_file),
            'record_file':str(file),'record_sha256':sha(file),**({'cost_evidence':record_evidence(native,POLICY)} if bounded else {})},exclusive=True)
        durable(policy_file,policy,exclusive=True)
    policy=read(policy_file);relative,raw=registry.object(policy_file);view=job/'certification-registry.json'
    if not view.exists():
        value={'schema_version':1,'format':'sss-experience-registry-v1','generation':0,'parent_digest':None,
            'reason':'independent File source execution','automatic_selection_uses_profile_id':False,
            'entries':[{'entry_id':policy['policy_digest'],'artifact_digest':policy['policy_digest'],'kind':'file_script',
                'payload':relative,'sha256':raw,'runtime_source':runtime,'state':'candidate','activated_generation':1}]}
        value['registry_digest']=digest(value);durable(view,value,exclusive=True)
    reviews=[];failures=[]
    for i in (0,1):
        record=run_material(cfg,job,'execute-cert-'+str(i),frames[i%len(frames)]['record'],'candidate_certification',view)
        frame(record);script_output_review(record,job)
        output_review=job/'output-reviews-v2'/record['session_id']/'result.json'
        audit=Path(record['run_dir'])/'experience-audit.jsonl';rows=[json.loads(l) for l in audit.read_text().splitlines()]
        if not complete_script_execution(policy,record,rows) or record.get('deferred'):failures.append(record['session_id'])
        file=root/'records'/(record['session_id']+'.json')
        reviews.append({'role':'candidate_certification','task_fingerprint':record['task_fingerprint'],
            'material_scope_file':str(job/'materials'/('execute-cert-'+str(i))/'script-material-scope.json'),
            'material_scope_sha256':sha(job/'materials'/('execute-cert-'+str(i))/'script-material-scope.json'),
            'record_file':str(file),'record_sha256':sha(file),'audit_sha256':sha(audit),
            'output_review_file':str(output_review),'output_review_sha256':sha(output_review),**({'cost_evidence':record_evidence(record,POLICY)} if bounded else {})})
    cert={'status':'rejected' if failures else 'certified_file_script_v4' if bounded else 'certified_file_script_v3','policy_digest':policy['policy_digest'],
        'payload_sha256':raw,'candidate_lock_file':str(job/'candidate-lock.json'),'candidate_lock_sha256':sha(job/'candidate-lock.json'),
        'native_review':read(native_file),'reviews':reviews,'failures':failures,'holdout_used':False,
        'quality_and_permission_required':True,'net_benefit_required':False,**({'accounting_policy':POLICY} if bounded else {})}
    certificate=job/'certificate.json'
    if not certificate.exists():durable(certificate,cert,exclusive=True)
    verify_script_certificate(policy,certificate,raw)
    entry=registry.entry('file_script',policy_file,runtime,certificate,verify_certificate=verify_script_certificate);state=registry.load()
    existing=next((e for e in state['entries'] if e['entry_id']==entry['entry_id']),None)
    if existing:
        if existing['state']!='active' or any(existing.get(k)!=entry.get(k) for k in ('sha256','certificate','runtime_source')):
            raise ValueError('existing script identity retained; no silent replacement')
        version=root/'registry'/read(root/'registry/current.json')['file']
    else:version=registry.publish([entry],expected=state['generation'],reason='ordinary source/tool-trace program independently certified')
    result={'policy_digest':policy['policy_digest'],'kind':'file_script','registry_file':str(version),
        'registry_sha256':sha(version),'certificate_sha256':sha(certificate),'opportunity_key':candidate['key'],
        'net_benefit_required':False,'holdout_used':False}
    durable(job/'activation.json',result,exclusive=True);state_event(root,'motif_activated',result);return result
