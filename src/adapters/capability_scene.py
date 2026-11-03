"""Shared offline adapter; scene subclasses provide evidence and native publication."""
from __future__ import annotations
import argparse
import copy
import hashlib
import json
import os
from pathlib import Path
import subprocess
import sys
import signal
import tempfile

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
from src.adapters.capability_improvement import evidence, read, save, run_improvement, validate
from src.adapters.capability_feedback import CapabilityFeedback,execution_cost
from src.adapters.capability_contract import capability_digest, capability_ref
from src.adapters.capability_materials import CapabilityMaterials


def reference(path):
    return {'path':str(path), 'sha256':hashlib.sha256(Path(path).read_bytes()).hexdigest()}


def run_child(args, **kwargs):
    """Own only this experiment's process group; never touch a service process."""
    child = subprocess.Popen(args, start_new_session=True, **kwargs)
    try:
        return child.wait()
    except BaseException:
        for sig in (signal.SIGINT, signal.SIGTERM, signal.SIGKILL):
            try: os.killpg(child.pid, sig)
            except ProcessLookupError: break
            try:
                child.wait(timeout=10)
                break
            except subprocess.TimeoutExpired: pass
        raise


class CapabilityImprovementAdapter:
    withdrawal_reasons=frozenset(('capability_legacy_changed','capability_revision_changed','capability_component_version_changed'))
    def __init__(self, plan):
        self.plan = copy.deepcopy(plan)
        self.seed = json.loads(evidence(plan['seed']))
        self.seed_catalog = json.loads(evidence(plan['seed_catalog']))
        if self.seed['owner'] != plan['owner']:
            raise ValueError('improvement_seed_owner_changed')
        self.feedback = CapabilityFeedback(plan.get('feedback_directory', str(Path(plan['store'])/'feedback')), plan['owner'])
        self.materials = CapabilityMaterials(Path(plan['store'])/'materials', plan['owner'])
        self.templates = {}
        self.pending_programs = {}
        self.configure_jobs(plan['jobs'])

    def configure_jobs(self,jobs):
        for job in jobs:
            template=self.freeze_publication_inputs(job)
            if 'program_learning' in template:
                self.validate_program_learning(template['program_learning'])
            self.templates[job['id']]=copy.deepcopy(template)

    @staticmethod
    def validate_program_learning(route):
        """Validate only host configuration; models never choose this route."""
        if (not isinstance(route,dict) or set(route)-{'backend','construction_cases','libraries'}
                or route.get('backend')!='script_motif' or not isinstance(route.get('libraries'),list)):
            raise ValueError('improvement_program_learning_route_invalid')
        cases=route.get('construction_cases')
        if not isinstance(cases,list) or len(cases)!=2:
            raise ValueError('improvement_program_two_training_cases_required')
        if len({row.get('id') for row in cases if isinstance(row,dict)})!=2:
            raise ValueError('improvement_program_independent_training_cases_required')
        for row in cases:
            if (not isinstance(row,dict) or set(row)!={'id','split','input','inputs'}
                    or not isinstance(row['id'],str) or not row['id'] or row['split']!='training'
                    or not isinstance(row['inputs'],list)):
                raise ValueError('improvement_program_training_case_invalid')
            for item in row['inputs']:
                if (not isinstance(item,dict) or set(item)!={'path','source'} or not isinstance(item['path'],str)
                        or item['path']!='/work/inputs/'+Path(item['path']).name):
                    raise ValueError('improvement_program_training_input_invalid')
                validate('evidence',item['source']);evidence(item['source'])
            if len({item['path'] for item in row['inputs']})!=len(row['inputs']):
                raise ValueError('improvement_program_training_input_duplicate')
        if len({capability_digest({'input':row['input'],'source_hashes':sorted(item['source']['sha256'] for item in row['inputs'])}) for row in cases})!=2:
            raise ValueError('improvement_program_independent_training_inputs_required')
        for ref in route['libraries']:validate('evidence',ref);evidence(ref)
        return route

    def freeze_publication_inputs(self,job):
        raise NotImplementedError('scene_freeze_publication_inputs_required')

    def inspect_run(self,entry,owner):
        raise NotImplementedError('scene_observation_adapter_required')

    def publish(self,job,candidate,attempt,expected_latest):
        raise NotImplementedError('scene_native_publication_required')

    def propose_opportunities(self, request, output):
        from src.adapters.capability_goal_proposal import propose
        factory=getattr(self,'opportunity_gate_factory',None)
        if factory is not None:
            # Acquire the original ledger lock only for this proposal; normal
            # construction subprocesses use the same cumulative ledger.
            with factory(request,output) as gate:return propose(request,output,gate)
        return propose(request,output,getattr(self,'opportunity_gate',None))

    def review_opportunity(self, proposal, request, output):
        # Host scene code supplies the independent quality contract. A model
        # cannot turn its own proposed interface into a publication validator.
        return {'decision':'pending','reason':'independent_goal_validation_required'}

    def acquire(self,job,result,attempt):
        """Opt-in native Script acquisition; publication remains scene-owned."""
        if not result.get('model_requested_program'):
            return {'status':'deferred','reason':'scene_learning_route_unavailable'}
        route=self.templates[job['id']].get('program_learning')
        if route is None:return {'status':'deferred','reason':'scene_program_learning_route_unavailable'}
        evidence(job['publication_plan']);self.validate_program_learning(route)
        if result.get('program_training_mode')!='bound_prefix_v1' or not result.get('composition_intent_ref'):
            return {'status':'deferred','reason':'scene_bound_program_intent_required'}
        from src.adapters.capability_program_training import prepare_program_cases,TrainingEvidenceUnavailable
        from src.adapters.capability_script_learning import learn
        from src.adapters.file_lock import exclusive_lock
        attempt=Path(attempt);task=json.loads(evidence(job['task']));snapshot=self.library()['snapshot']
        if result.get('construction_snapshot_sha256')!=snapshot['digest']:
            return {'status':'deferred','reason':'scene_program_construction_snapshot_changed'}
        program_ref=reference(result['program_request']);program=json.loads(evidence(program_ref))
        intent_ref=result['composition_intent_ref'];intent=json.loads(evidence(intent_ref))
        if (not isinstance(program,dict) or set(program)!={'source','description','mode','interface'}
                or program.get('mode')!='json' or program.get('interface')!='function_v1'):
            raise ValueError('improvement_program_json_function_required')
        if (intent.get('task_sha256')!=capability_digest(task) or intent.get('program_sha256')!=capability_digest(program)
                or intent.get('construction_snapshot_sha256')!=snapshot['digest'] or intent.get('owner')!=self.plan['owner']):
            raise ValueError('improvement_program_intent_changed')
        # This host executor presently supports Script leaves. Other native
        # adapters remain extension points, never silently rerouted as Script.
        lookup={cap['id']:cap for cap in snapshot['capabilities']};pending=[]
        for step in intent['steps']:
            if step['capability']=='$program':break
            pending.append(step['capability'])
        seen=set();unsupported=set()
        while pending:
            ref=pending.pop()
            if ref['id'] in seen:continue
            seen.add(ref['id']);cap=lookup.get(ref['id'])
            if cap is None:raise ValueError('improvement_program_prefix_reference_missing')
            if cap['implementation']['kind']=='legacy':
                backend=cap['implementation']['legacy_ref'].get('backend')
                if backend!='script_motif':unsupported.add(backend or 'unknown')
            pending.extend(cap['dependencies'])
        if unsupported:return {'status':'deferred','reason':'scene_program_prefix_backend_unsupported','backends':sorted(unsupported)}
        refs=[job['task'],job['publication_plan'],reference(attempt/'result.json'),program_ref,intent_ref]
        for key in ('capability_source_ref','capability_source_encoding_ref'):
            if not result.get(key):raise ValueError('improvement_program_source_evidence_required')
            refs.append(result[key])
        refs.extend(reference(ROOT/name) for name in ('src/adapters/capability_script_learning.py',
            'src/adapters/capability_program_training.py','src/adapters/capability_script_execution.py',
            'src/adapters/capability_source_authoring.py','src/adapters/capability_program_encoding.py',
            'src/adapters/script_motif_compiler.py','scripts/certify-script-motifs.mjs'))
        for ref in refs:evidence(ref)
        libraries=copy.deepcopy(route['libraries'])+[row['library'] for row in self.materials.records() if row['backend']=='script_motif']
        key=capability_digest({'opportunity':self.opportunity_key(job),'route':route,'source':refs,'snapshot':snapshot['digest']})
        directory=self.materials.directory/'acquisitions'/key;directory.mkdir(parents=True,exist_ok=True,mode=0o700)
        with exclusive_lock(directory/'.lock'):
            if (directory/'request.json').exists():
                return {'status':'deferred','reason':'scene_program_acquisition_already_attempted','request':reference(directory/'request.json')}
            save(directory/'request.json',{'format':'capability_program_acquisition_request_v1','job':job['id'],
                'route':route,'source':refs,'snapshot_sha256':snapshot['digest'],'model_requests':0})
            try:
                training=prepare_program_cases(task,snapshot,program_ref,intent_ref,route['construction_cases'],
                    libraries,directory/'program-training',source_refs=refs)
                for ref in refs:evidence(ref)
                library=learn(program,training['cases'],directory/'native',result['capability_source_ref'])
                observations=reference(directory/'native/observations.json')
                probe=subprocess.run(['node','scripts/run-script-capability.mjs','--catalog','--library',library['path'],
                    '--owner',self.plan['owner']],cwd=ROOT,capture_output=True,text=True,encoding='utf-8',check=True)
                if not json.loads(probe.stdout)['capabilities']:raise ValueError('improvement_program_no_certified_material')
                continuation={'format':'capability_program_acquisition_continuation_v1','task_sha256':capability_digest(task),
                    'program_ref':program_ref,'composition_intent_ref':intent_ref,'library':library,'observations':observations,
                    'capability_source_ref':result['capability_source_ref'],
                    'capability_source_encoding_ref':result['capability_source_encoding_ref']}
                save(directory/'continuation.json',continuation);continuation_ref=reference(directory/'continuation.json')
                admission_refs=[*refs,reference(directory/'request.json'),training['evidence'],
                    reference(directory/'native/certification.json'),observations,continuation_ref]
                for ref in admission_refs:evidence(ref)
                material=self.materials.register(backend='script_motif',library=library,refs=admission_refs,
                    acquisition_key=key,opportunity=self.opportunity_key(job))
                self.pending_programs[capability_digest(task)]=continuation_ref
                outcome={'status':'registered','material':material,'continuation':continuation_ref,
                    'model_requests':0,'observed_model_usd':0,'benefit':None}
            except TrainingEvidenceUnavailable as error:
                outcome={'status':'deferred','reason':str(error),'model_requests':0,'benefit':None}
            except Exception as error:
                outcome={'status':'deferred','reason':str(error),'model_requests':0,'benefit':None,
                    'diagnostics':{'kind':'native_material_acquisition','error':str(error)}}
                if getattr(error,'program_training_evidence_ref',None):outcome['program_training_ref']=error.program_training_evidence_ref
                source=getattr(error,'script_diagnostics',None);prefix=getattr(error,'program_training_diagnostics',None)
                if source:outcome['diagnostics']['source']=copy.deepcopy(source)
                if prefix:outcome['diagnostics']['prefix']=copy.deepcopy(prefix)
                # A diagnostic attribute is not itself permission to repair an
                # unknown runtime failure. Only located source/admission or
                # verified data/binding errors go to the existing model repair.
                source_error=isinstance(source,dict) and source.get('kind')=='script_admission'
                binding_error=isinstance(prefix,dict) and prefix.get('kind')=='construction_prefix_compile'
                if isinstance(prefix,dict) and prefix.get('kind')=='construction_prefix':
                    binding_error=any(row.get('verified_call_binding') is True and row.get('argument_shapes') is not None
                        and (row.get('diagnostic') or {}).get('category')=='data_operation_error'
                        and (row.get('diagnostic') or {}).get('exception_type') in ('TypeError','KeyError','IndexError')
                        for row in prefix.get('worker_failures',[]) if isinstance(row,dict))
                if source_error or binding_error:
                    issues=([{'path':['program','source'],'line':source.get('line'),'column':source.get('column'),
                        'expected':'native-admitted source','actual':source.get('error')}] if source_error
                        else copy.deepcopy(prefix.get('diagnostics',{}).get('issues',[])))
                    outcome['diagnostics']['issues']=issues
                    outcome.update(status='failed',error=str(error),repairable=True)
            save(directory/'result.json',outcome);return outcome

    def freeze(self, directory):
        observations=[(entry,self.inspect_run(entry,self.plan['owner'])) for entry in self.plan.get('discovery',[])]
        for entry,observation in observations:
            if observation.get('capability_execution') is True or observation['kind']=='capability_execution':
                trace=observation['trace']
                self.feedback.observe(stage='execution',subject=trace['root'],scope=observation['scope'],
                    status=observation['status'],cost=execution_cost(observation),evidence=observation['evidence'])
                # Generic runtime guards report the selected root, not the exact
                # corrupt leaf. Quarantine that root; do not guess leaf blame.
                if any(r.get('reason') in self.withdrawal_reasons for r in trace.get('receipts',[])):
                    self.feedback.withdraw(trace['root'],'runtime_version_guard_failed',reference(Path(entry['run'])/'trace.json'))
        save(Path(directory)/'scene-context.json', {'seed':self.seed,
            'source_catalog':self.seed_catalog, 'publication_inputs':self.templates})

    def discover_jobs(self,directory):
        entries=self.plan.get('discovery',[])
        if not entries:return []
        from src.adapters.capability_discovery import discover_jobs
        jobs=discover_jobs(entries,self.plan['owner'],Path(directory)/'discovery',inspector=self.inspect_run)
        self.configure_jobs(jobs)
        save(Path(directory)/'discovered-publication-inputs.json',self.templates)
        return jobs

    def prioritize_jobs(self,jobs):
        return self.feedback.prioritize(jobs)

    @staticmethod
    def opportunity_key(job):
        # Generated wrapper paths change between runs; original evidence does not.
        identity=job.get('source_evidence') or {'task':job['task'],'observations':job['observations']}
        return job['id']+':'+capability_digest(identity)

    def admission(self,job):
        key=self.opportunity_key(job)
        facts=[f for f in self.feedback.read()['facts'].values() if f['stage']=='attempt' and f['opportunity']==key]
        if any(f['status']=='passed' for f in facts):return 'skip','same_evidence_already_published'
        gaps=[f for f in facts if f['status']=='unknown']
        if gaps:
            current=self.library()['snapshot']['digest']
            if any(not f.get('subject') or f['subject'].get('construction_snapshot_sha256') in (None,current) for f in gaps):
                return 'defer','construction_gap_requires_new_material_or_evidence'
        failed=[f for f in facts if f['status']=='failed']
        if len(failed)>=2:
            # Failure with the old vocabulary must not block an opportunity
            # after newly certified materials change its construction snapshot.
            # Older facts did not store the snapshot in subject; recover it
            # from their immutable attempt evidence, conservatively retaining
            # unscoped failures when no snapshot was recorded.
            snapshots=[(f.get('subject') or {}).get('construction_snapshot_sha256') or
                       json.loads(evidence(f['evidence'][0])).get('construction_snapshot_sha256') for f in failed]
            current=self.library()['snapshot']['digest'] if any(snapshots) else None
            if sum(s is None or s==current for s in snapshots)>=2:
                return 'defer','failed_opportunity_requires_new_evidence'
        return 'start','feedback_allows_trial'

    def pending_gap(self,job):
        """Return original gap evidence for a previously deferred opportunity."""
        key=self.opportunity_key(job);current=self.library()['snapshot']['digest']
        for fact in self.feedback.read()['facts'].values():
            if fact['stage']=='attempt' and fact['opportunity']==key and fact['status']=='unknown' and (fact.get('subject') or {}).get('construction_snapshot_sha256')==current:
                ref=fact['evidence'][0];result=json.loads(evidence(ref))
                if result.get('status')=='deferred' and result.get('construction_gap'):
                    return result,ref
        return None

    def record_outcome(self,job,attempt,result,candidate,outcome):
        passed=outcome is not None and outcome['status']=='published'
        key=self.opportunity_key(job)
        refs=[reference(attempt/'result.json')]
        if outcome and outcome.get('evidence_ref'):refs.append(outcome['evidence_ref'])
        scope=job.get('feedback_key',job['id'])
        self.feedback.observe(stage='attempt',subject={'construction_snapshot_sha256':result['construction_snapshot_sha256']} if result.get('construction_snapshot_sha256') else None,scope=scope,status='passed' if passed else 'unknown' if result.get('status')=='deferred' else 'failed',
            cost=result.get('observed_model_usd'),evidence=refs,opportunity=key)
        if outcome and outcome.get('committed') and not passed and candidate:
            self.feedback.withdraw(capability_ref(candidate['capability']),'committed_followup_failed',refs[-1])
        if passed:
            root=capability_ref(candidate['capability'])
            for ref in candidate['capability']['dependencies']:
                self.feedback.observe(stage='construction',subject=ref,beneficiary=root,scope=scope,
                    status='passed',evidence=refs)
            self.feedback.observe(stage='execution',subject=root,scope=job.get('execution_scope',scope),status='passed',
                cost=None if outcome.get('execution_cost') is None else execution_cost(outcome['execution_cost']),evidence=refs)

    def raw_library(self):
        evidence(self.plan['seed'])
        with tempfile.TemporaryDirectory(prefix='capability-materials-') as directory:
            index=Path(directory)/'index.json';save(index,self.materials.export())
            result = subprocess.run(['node', '--experimental-strip-types',
                'scripts/export-capability-construction-library.mjs', self.plan['store'], self.plan['seed']['path'],str(index)],
                cwd=ROOT, capture_output=True, text=True, encoding='utf-8', check=True)
        value = json.loads(result.stdout)
        value['source_catalog'] = {'seed':self.seed_catalog,'admitted_materials':value.pop('material_catalog',[])}
        return value

    def library(self):
        value=self.feedback.project(self.raw_library())
        if value['snapshot'] is None:raise ValueError('feedback_no_available_capability')
        return value

    def construction_budget(self,job):
        """Expose a trusted finite research gate, never platform null as zero."""
        from .capability_construction_history import amount
        budget=getattr(getattr(self,'gate',None),'budget',None)
        if budget is None:return None
        limit=amount(budget.limit);spent=amount(budget.spent)
        pending=sum((amount(value) for value in budget.pending.values()),start=amount(0))
        return {'limit_usd':str(limit),'spent_usd':str(spent),'pending_usd':str(pending),
                'remaining_usd':str(max(amount(0),limit-spent-pending))}

    def construct(self, task, library, output, parent, feedback):
        reconsider=library.get('source_catalog',{}).get('construction_feedback',{}).get('reconsider') is True
        pending=self.pending_programs.pop(capability_digest(task),None) if parent is None else None
        continuation_ref=None if reconsider else pending
        if continuation_ref is None and parent is None and not reconsider:
            # Persisted continuation evidence also supports a resumed public
            # controller; aliases from the original source are never replayed.
            continuation=library.get('source_catalog',{}).get('material_continuation',{})
            for ref in reversed(continuation.get('acquisitions',[])):
                record=json.loads(evidence(ref))
                for source in record.get('evidence',[]):
                    value=json.loads(evidence(source))
                    if value.get('status')=='registered' and value.get('continuation'):
                        candidate=json.loads(evidence(value['continuation']))
                        if candidate.get('task_sha256')==capability_digest(task):continuation_ref=value['continuation'];break
                if continuation_ref is not None:break
        if continuation_ref is not None:
            from src.adapters.capability_program_encoding import encode_program_composition
            from src.adapters.capability_authoring import compact_proposal,diagnose
            from src.adapters.capability_proposal import prepare_attempt,write
            pending=json.loads(evidence(continuation_ref))
            if pending.get('format')!='capability_program_acquisition_continuation_v1' or pending.get('task_sha256')!=capability_digest(task):
                raise ValueError('improvement_program_continuation_changed')
            catalog=self.construction_catalog(library)
            effective,_=prepare_attempt(task=task,catalog=catalog,snapshot=library['snapshot'],output=output)
            effective.update(model_called=False,host_encoding='frozen_program_composition')
            write(output/'effective.json',effective)
            result={'status':'failed','construction_snapshot_sha256':library['snapshot']['digest'],
                'model_called':False,'provider_requests':0,'request_ids':[],'observed_model_usd':0,
                'observed_model_usd_decimal':'0','billing_usd':None,'elapsed_seconds':0,
                'originating_program_ref':pending['program_ref'],'originating_composition_intent_ref':pending['composition_intent_ref'],
                'originating_source_ref':pending['capability_source_ref'],'acquisition_continuation_ref':continuation_ref,
                'publication_authorized':False,'quality':'not_independently_reviewed'}
            try:
                encoded=encode_program_composition(task,library['snapshot'],pending['program_ref'],pending['composition_intent_ref'],
                    pending['library'],pending['observations'])
                write(output/'proposal.json',encoded['proposal']);write(output/'candidate.json',encoded['candidate'])
                write(output/'answer.txt',json.dumps(compact_proposal(encoded['proposal'],task,library['snapshot'])))
                result.update(status='compiled_candidate',candidate_path=str(output/'candidate.json'),candidate_id=encoded['candidate']['capability']['id'],
                    host_encoding=encoded['encoding_scope'],reusability_verified=False)
            except ValueError as error:
                result.update(error=str(error),diagnostics=diagnose(error))
                repair=getattr(error,'program_composition_repair_context',None)
                if repair is not None:
                    write(output/'composition-repair-context.json',repair)
                    result['composition_repair_context_ref']=reference(output/'composition-repair-context.json')
                write(output/'answer.txt',json.dumps({'format':'capability_host_encoding_failure_v1','error':str(error),
                    'originating_source_ref':pending['capability_source_ref']}))
            write(output/'result.json',result);return result
        gate=getattr(self,'gate',None)
        if gate is not None:
            from .capability_proposal import propose_once
            gate.register_attempt(output,self.plan['id']+'/'+str(output.relative_to(Path(self.plan['output']))))
            return propose_once(task=task,catalog=self.construction_catalog(library),snapshot=library['snapshot'],
                output=output,gate=gate,repair_from=parent,feedback=feedback)
        context = output.parent/(output.name+'-context'); context.mkdir(mode=0o700)
        save(context/'task.json', task); save(context/'snapshot.json', library['snapshot'])
        # Preserve original leaf descriptions/examples and append verified learned
        # contracts. A model is free to use a primitive, a learned C, or neither.
        save(context/'catalog.json', self.construction_catalog(library))
        args = [sys.executable, str(ROOT/'src/adapters/capability_proposal.py'),
                '--task',str(context/'task.json'),'--catalog',str(context/'catalog.json'),
                '--snapshot',str(context/'snapshot.json'),'--output',str(output),
                '--ledger-root',self.plan['ledger_root'],'--call-model']
        if parent:
            save(context/'feedback.json', feedback)
            args += ['--repair-from',str(parent),'--feedback',str(context/'feedback.json')]
        with (context/'stdout.json').open('w') as out, (context/'stderr.log').open('w') as err:
            run_child(args, cwd=ROOT, stdout=out, stderr=err)
        return read(output/'result.json')

    @staticmethod
    def construction_catalog(library):
        return {'source_catalog':library.get('source_catalog',{}),
            'learned_and_seed_capabilities':library.get('catalog',[]),
            'preferred_roots':library.get('selection',{}).get('construction',[])}



def load_scene_adapter(plan):
    """Only a host-authored plan may select executable adapter code.

    This is equivalent to installing an MCP integration, not a model proposal
    extension. Pin adapter bytes before import and recheck before each action.
    """
    for dependency in plan.get('scene_dependencies',[]):evidence(dependency)
    ref=plan.get('scene_adapter')
    if ref is None:
        from scenarios.remotion_edit.structured.run_capability_improvement import SourceImprovementAdapter
        return SourceImprovementAdapter(plan)
    import importlib.util
    raw=evidence(ref)
    path=Path(ref['path']).resolve()
    if path.suffix!='.py':raise ValueError('scene_adapter_python_module_required')
    module_name='geneloop_scene_'+hashlib.sha256(raw).hexdigest()
    spec=importlib.util.spec_from_file_location(module_name,path)
    module=importlib.util.module_from_spec(spec)
    # Execute precisely the checked bytes; don't reopen changed source or pyc.
    sys.modules[module_name]=module
    try:exec(compile(raw,str(path),'exec'),module.__dict__)
    except BaseException:
        sys.modules.pop(module_name,None)
        raise
    adapter=module.create_adapter(copy.deepcopy(plan))
    if not isinstance(adapter,CapabilityImprovementAdapter):raise ValueError('scene_adapter_contract_required')
    return adapter
