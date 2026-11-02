"""Frontier experiment adapter on the existing improvement controller."""
from __future__ import annotations
import copy,json,os,subprocess,sys
from pathlib import Path
from src.adapters.capability_scene import CapabilityImprovementAdapter,ROOT,reference,run_child
from src.adapters.capability_improvement import evidence,read,save
from src.adapters.capability_contract import capability_digest,create_capability_snapshot
from src.adapters.capability_proposal import write
from src.adapters import capability_proposal as pilot
from src.adapters.capability_authoring import compact_proposal,diagnose
from src.adapters.capability_program_encoding import encode_complete_script,encode_program_composition
from scenarios.paper_proofreading.frontier.author import propose
from scenarios.paper_proofreading.frontier.learn import learn


class FrontierAdapter(CapabilityImprovementAdapter):
    def freeze_publication_inputs(self,job):
        template=json.loads(evidence(job['publication_plan']))
        for ref in template['libraries']+template.get('pinned_evidence',[]):evidence(ref)
        for label in ('validation','followup'):
            for item in template[label]['inputs']:evidence(item['source'])
        for cases in template['native_cases'].values():
            for case in cases:
                for item in case['inputs']:evidence(item['source'])
        return template

    def library(self):
        value=super().library()
        # Pin examples into the same repair-context hash as the visible catalog.
        examples=next(iter(self.templates.values()))['program_examples']
        value['source_catalog']['program_examples']=copy.deepcopy(examples)
        value['program_examples']=copy.deepcopy(examples)
        template=next(iter(self.templates.values()))
        value['presentation']=copy.deepcopy(template.get('presentation',{}))
        value['program_input_schemas']=copy.deepcopy(template.get('program_input_schemas',{}))
        value['source_catalog']['presentation']=value['presentation']
        value['source_catalog']['program_input_schemas']=value['program_input_schemas']
        if value['presentation'].get('hide_redundant_JSON_file_variants'):
            snapshot=value['snapshot'];caps={c['id']:c for c in snapshot['capabilities']}
            values={capability_digest(c['implementation']['legacy_ref']) for c in caps.values()
                if c['implementation']['kind']=='legacy' and 'value' in c['contract']['input_schema'].get('properties',{})}
            roots=[r for r in snapshot['roots'] if not (caps[r['id']]['implementation']['kind']=='legacy' and
                'paths' in caps[r['id']]['contract']['input_schema'].get('properties',{}) and
                capability_digest(caps[r['id']]['implementation']['legacy_ref']) in values)]
            selected={};todo=list(roots)
            while todo:
                ref=todo.pop()
                if ref['id'] in selected:continue
                selected[ref['id']]=caps[ref['id']];todo.extend(caps[ref['id']]['dependencies'])
            value['snapshot']=create_capability_snapshot(snapshot['owner'],roots,list(selected.values()))
        return value

    def construct(self,task,library,output,parent,feedback):
        expected=getattr(self,'expected_initial_snapshot_sha256',None)
        if expected is not None:
            if library['snapshot']['digest']!=expected:raise ValueError('frontier_study_initial_exposure_changed')
            self.expected_initial_snapshot_sha256=None
        template=next(iter(self.templates.values()));pending=getattr(self,'pending_complete',None)
        self.pending_complete=None
        if pending and (pending.get('composition_intent_ref') or template.get('auto_wrap_complete_program')):
            encoded=None;encoding_error=None
            try:
                if pending.get('composition_intent_ref'):
                    encoded=encode_program_composition(task,library['snapshot'],pending['program_ref'],
                        pending['composition_intent_ref'],pending['library'],pending['observations'])
                else:
                    encoded=encode_complete_script(task,library['snapshot'],pending['library'],pending['observations'])
            except ValueError as error:
                if not pending.get('composition_intent_ref'):raise
                encoding_error=error
            if encoded or encoding_error:
                self.gate.register_attempt(output,self.plan['id']+'/'+str(output.relative_to(Path(self.plan['output']))))
                effective,_=pilot.prepare_attempt(task=task,catalog=library['source_catalog'],snapshot=library['snapshot'],output=output)
                scope=encoded['encoding_scope'] if encoded else 'model_explicit_composition_encoding_failed'
                effective.update(model_called=False,host_encoding=scope);write(output/'effective.json',effective)
                result={'status':'failed','construction_snapshot_sha256':library['snapshot']['digest'],
                    'model_called':False,'provider_requests':0,'request_ids':[],
                    'observed_model_usd':0,'observed_model_usd_decimal':'0','elapsed_seconds':0,
                    'host_encoding':scope,'originating_program':pending['program'],
                    'originating_program_ref':pending['program_ref'],'quality':'not_independently_reviewed'}
                if pending.get('composition_intent_ref'):
                    result['originating_composition_intent_ref']=pending['composition_intent_ref']
                if encoding_error:
                    result['originating_answer_ref']=pending['answer_ref']
                    repair_context=getattr(encoding_error,'program_composition_repair_context',None)
                    if repair_context is not None:
                        write(output/'composition-repair-context.json',repair_context)
                        result['composition_repair_context_ref']=reference(output/'composition-repair-context.json')
                    # The original answer names aliases from an older pool.
                    # Preserve its source reference, never present it as the
                    # answer authored against this new snapshot.
                    write(output/'answer.txt',json.dumps({'format':'capability_host_encoding_failure_v1',
                        'error':str(encoding_error),'originating_answer_ref':pending['answer_ref'],
                        'originating_composition_intent_ref':pending['composition_intent_ref']}))
                    result.update(error=str(encoding_error),diagnostics=diagnose(encoding_error))
                    write(output/'result.json',result);return result
                write(output/'proposal.json',encoded['proposal']);write(output/'candidate.json',encoded['candidate'])
                write(output/'answer.txt',json.dumps(compact_proposal(encoded['proposal'],task,library['snapshot'])))
                result.update(status='compiled_candidate',candidate_id=encoded['candidate']['capability']['id'])
                write(output/'result.json',result);return result
        result=propose(task=task,library=library,output=output,gate=self.gate,parent=parent,feedback=feedback,
                       owner_id=self.plan['id']+'/'+str(output.relative_to(Path(self.plan['output']))))
        if result.get('program_request'):
            program=read(output/'program.json');template=next(iter(self.templates.values()))
            try:
                result['native_library']=learn(program,template['native_cases'][program['mode']],output/'native',
                    reference(output/'answer.txt'),large_output=True)
                result['native_observations']=reference(output/'native/observations.json')
                self.pending_complete={'library':result['native_library'],'observations':result['native_observations'],
                    'program':program,'program_ref':reference(output/'program.json'),
                    'answer_ref':reference(output/'answer.txt'),
                    'composition_intent_ref':result.get('composition_intent_ref')}
            except Exception as error:
                diagnostics={'native_error':str(error)}
                for p in (output/'native').glob('**/certification.json'):diagnostics['certification']=read(p)
                for p in (output/'native').glob('**/admission-error.json'):diagnostics['admission']=read(p)
                for p in (output/'native').glob('**/source-stderr.txt'):
                    text=p.read_text()
                    if 'Traceback' in text or 'Error:' in text:diagnostics[p.parent.name+'_stderr']=text[-6000:]
                result.update(status='failed',error='frontier_native_material_rejected',diagnostics=diagnostics)
            write(output/'result.json',result)
        return result

    def acquire(self,job,result,attempt):
        if not result.get('native_library'):return {'status':'deferred','reason':'frontier_no_certified_material'}
        refs=[reference(attempt/'answer.txt'),reference(attempt/'native/certification.json'),job['publication_plan']]
        if result.get('composition_intent_ref'):refs.append(result['composition_intent_ref'])
        if result.get('native_observations'):refs.append(result['native_observations'])
        material=self.materials.register(backend='script_motif',library=result['native_library'],refs=refs,
            acquisition_key=capability_digest(refs),opportunity=self.opportunity_key(job))
        return {'status':'registered','material':material,'model_requests':0,'benefit':None}

    def publish(self,job,candidate,attempt,expected_latest):
        source=copy.deepcopy(self.templates[job['id']]);plan={'owner':self.plan['owner'],'store':self.plan['store'],
            'candidate':str(attempt/'candidate.json'),'expected_latest':expected_latest,'output':str(attempt/'publication')}
        libraries=source['libraries']+[r['library'] for r in self.materials.records() if r['backend']=='script_motif']
        for ref in libraries:evidence(ref)
        for label in ('validation','followup'):
            task=source[label];workspace=attempt/(label+'-workspace');(workspace/'inputs').mkdir(parents=True,mode=0o700)
            inputs=[]
            for item in task['inputs']:
                path=item['path']
                if path!='/work/inputs/'+Path(path).name:raise ValueError('frontier_input_path_invalid')
                raw=evidence(item['source']);target=workspace/'inputs'/Path(path).name
                with target.open('xb') as stream:stream.write(raw)
                target.chmod(0o400);inputs.append({'path':path,'sha256':reference(target)['sha256']})
            plan[label]={'id':task['id']+'-'+job['id']+'-'+attempt.name,'workspace':str(workspace.resolve()),
                'input':task['input'],'specification':task['specification'],
                'manifest':{'format':'script_capability_task_v1','libraries':libraries,'inputs':inputs}}
        save(attempt/'publication-plan.json',plan)
        with (attempt/'publication-stdout.log').open('w') as out,(attempt/'publication-stderr.log').open('w') as err:
            code=run_child(['node','--experimental-strip-types',str(Path(__file__).with_name('publish.mjs')),str(attempt/'publication-plan.json')],
                cwd=ROOT,env={**os.environ,'SSS_PYTHON':sys.executable},stdout=out,stderr=err)
        directory=Path(plan['output']);path=directory/'result.json'
        result=read(path) if path.exists() else {'error':'frontier_publication_process_failed'}
        ref=reference(path if path.exists() else attempt/'publication-stderr.log')
        if code==0 and result.get('status')=='completed':
            return {'status':'published','publication_sha256':result['publication_sha256'],'evidence_ref':ref}
        feedback={}
        runtime_binding_failure=False
        for label in ('validation','followup'):
            p=directory/label/'validation.json'
            if p.exists() and not read(p)['passed']:feedback=read(p);break
            trace_path=directory/label/'trace.json'
            if trace_path.exists():
                trace=read(trace_path)
                failures=[{'capability':r['capability'],'reason':r.get('reason'),'call_id':r['call_id']}
                    for r in trace.get('receipts',[]) if r.get('reason') in ('script_capability_input_not_granted','script_capability_input_contract_mismatch')]
                if failures:
                    runtime_binding_failure=True
                    feedback={'checks':[{'id':'granted_input_binding','status':'failed','observation':{
                        'failed_calls':failures,'current_task_arguments':plan[label]['input'],
                        'granted_inputs':plan[label]['manifest']['inputs'],
                        'requirement':'Bind existing file-reading capabilities to current task inputs, not new-program ABI placeholders.'}}]}
                    break
        return {'status':'failed','error':result.get('error','frontier_publication_failed'),
            'committed':(directory/'publication.json').exists(),'evidence_ref':ref,
            'repairable':result.get('error')=='capability_store_validation_failed' or runtime_binding_failure,'feedback':feedback}


def create_adapter(plan):return FrontierAdapter(plan)
