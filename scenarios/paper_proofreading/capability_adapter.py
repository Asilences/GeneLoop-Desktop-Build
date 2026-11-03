"""Paper Script adapter. Reuses common discovery, Builder, feedback and Store."""
import copy
import hashlib
import json
import os
from pathlib import Path
import sys
import subprocess
from src.adapters.capability_scene import CapabilityImprovementAdapter,ROOT,run_child,reference
from src.adapters.capability_improvement import evidence,read,save
from src.adapters.capability_contract import capability_digest,validate_capability_snapshot
from src.adapters.capability_discovery import read_context
from scenarios.paper_proofreading.verify_capability_outputs import verify
from src.adapters.capability_trajectory import project_web_task
from src.adapters.file_lock import exclusive_lock


class PaperCapabilityAdapter(CapabilityImprovementAdapter):
    withdrawal_reasons=CapabilityImprovementAdapter.withdrawal_reasons|{'script_capability_leaf_changed'}

    def acquire(self,job,result,attempt):
        if result.get('model_requested_program'):return super().acquire(job,result,attempt)
        gap=result.get('construction_gap') or {};ref=self.plan.get('learning_routes')
        if gap.get('reason')!='missing_primitive' or not ref:
            return {'status':'deferred','reason':'paper_learning_route_unavailable'}
        config=json.loads(evidence(ref))
        if config.get('format')!='paper_script_learning_routes_v1' or config.get('owner')!=self.plan['owner']:
            raise ValueError('paper_learning_route_invalid')
        routes=[r for r in config['routes'] if r['scope']==job.get('execution_scope')]
        if len(routes)!=1:return {'status':'deferred','reason':'paper_learning_route_ambiguous_or_absent'}
        route=routes[0];rows=route['tasks']
        if route.get('backend')!='script_motif' or len(rows)<2 or rows[0]['role']!='certification' or any(r['role']!='training' for r in rows[1:]):
            raise ValueError('paper_learning_partition_invalid')
        refs=[ref];identities=set()
        for row in rows:
            observed=project_web_task(row['path'],self.plan['owner'])
            if observed['status']!='completed' or observed['scene']!='paper-proofreading' or observed['task_id'] in identities:
                raise ValueError('paper_learning_independent_completed_tasks_required')
            identities.add(observed['task_id'])
            if any(r not in row['evidence'] for r in observed['evidence']):raise ValueError('paper_learning_unpinned_evidence')
            for r in row['evidence']:evidence(r)
            refs.extend(row['evidence'])
        files=['scripts/learn-script-motifs.py','scripts/certify-script-motifs.mjs','src/adapters/script_motif_compiler.py',
               'src/adapters/script_dataflow_compiler.py','src/adapters/reuse_snapshot.py']
        refs.extend(reference(ROOT/name) for name in files)
        key=capability_digest({'route':route,'evidence':refs});directory=self.materials.directory/'acquisitions'/key
        directory.mkdir(parents=True,exist_ok=True,mode=0o700)
        with exclusive_lock(directory/'.lock'):
            if (directory/'request.json').exists():return {'status':'deferred','reason':'paper_learning_already_attempted'}
            save(directory/'request.json',{'job':job['id'],'gap':gap,'route':route,'evidence':refs,'model_requests':0})
            try:
                command=[sys.executable,str(ROOT/files[0]),*[a for row in rows for a in ('--task',row['path'])],'--output',str(directory/'learn')]
                with (directory/'stdout.log').open('w') as out,(directory/'stderr.log').open('w') as err:
                    code=run_child(command,cwd=ROOT,env={**os.environ,'SSS_PYTHON':sys.executable},stdout=out,stderr=err)
                if code:raise ValueError('paper_native_learning_failed')
                library=reference(directory/'learn/library.json')
                probe=subprocess.run(['node','scripts/run-script-capability.mjs','--catalog','--library',library['path'],'--owner',self.plan['owner']],
                    cwd=ROOT,capture_output=True,text=True,check=True, encoding='utf-8')
                if not json.loads(probe.stdout)['capabilities']:raise ValueError('paper_learning_no_supported_material')
                for r in refs:evidence(r)
                refs += [reference(directory/'request.json'),reference(directory/'learn/certification.json')]
                material=self.materials.register(backend='script_motif',library=library,refs=refs,acquisition_key=key,opportunity=self.opportunity_key(job))
                outcome={'status':'registered','material':material,'model_requests':0,'benefit':None}
            except Exception as error:outcome={'status':'deferred','reason':str(error),'benefit':None}
            save(directory/'result.json',outcome);return outcome

    def freeze_publication_inputs(self,job):
        plan=json.loads(evidence(job['publication_plan']))
        for ref in plan['libraries']:evidence(ref)
        for label in ('validation','followup'):
            for item in plan[label]['inputs']:evidence(item['source'])
        return plan

    def inspect_run(self,entry,owner):
        if entry['kind']!='paper_capability_execution' or entry['role'] not in ('training','validation'):
            raise ValueError('paper_observation_scope_invalid')
        run=Path(entry['run']);context=read_context(entry['context'],owner)
        manifest,trace,args,snapshot,spec=[read(run/name) for name in ('manifest.json','trace.json','args.json','snapshot.json','specification.json')]
        validate_capability_snapshot(snapshot,owner)
        if trace['owner']!=owner or trace['mode']!='execute' or trace['snapshot_sha256']!=snapshot['digest'] or trace['arguments_sha256']!=capability_digest(args):
            raise ValueError('paper_observation_binding_changed')
        passed=verify(manifest,trace,spec)['passed']
        refs=[entry['context'],*[reference(run/name) for name in ('manifest.json','trace.json','args.json','snapshot.json','specification.json')]]
        return {'kind':'paper_capability_execution','capability_execution':True,'task_id':trace['task_id'],
            'task_fingerprint':capability_digest(sorted(i['sha256'] for i in manifest['inputs'])),
            'status':'passed' if passed else 'failed','context':context,'scope':context['scope'],
            'evidence':refs,'trace':trace,'role':entry['role']}

    def publish(self,job,candidate,attempt,expected_latest):
        source=copy.deepcopy(self.templates[job['id']]);plan={
            'owner':self.plan['owner'],'store':self.plan['store'],'candidate':str(attempt/'candidate.json'),
            'expected_latest':expected_latest,'output':str(attempt/'publication')}
        libraries=source['libraries']+[r['library'] for r in self.materials.records() if r['backend']=='script_motif']
        for ref in libraries:evidence(ref)
        for label in ('validation','followup'):
            task=source[label];workspace=attempt/(label+'-workspace');(workspace/'inputs').mkdir(parents=True,mode=0o700)
            inputs=[]
            for item in task['inputs']:
                path=item['path']
                if path!='/work/inputs/'+Path(path).name:raise ValueError('paper_input_path_invalid')
                raw=evidence(item['source']);target=workspace/'inputs'/Path(path).name
                with target.open('xb') as stream:stream.write(raw)
                target.chmod(0o400);inputs.append({'path':path,'sha256':hashlib.sha256(raw).hexdigest()})
            plan[label]={'id':task['id']+'-'+job['id']+'-'+attempt.name,'workspace':str(workspace.resolve()),
                'input':task['input'],'specification':task['specification'],
                'manifest':{'format':'script_capability_task_v1','libraries':libraries,'inputs':inputs}}
        save(attempt/'publication-plan.json',plan)
        with (attempt/'publication-stdout.log').open('w') as out,(attempt/'publication-stderr.log').open('w') as err:
            code=run_child(['node','--experimental-strip-types',str(Path(__file__).with_name('publish_capability.mjs')),str(attempt/'publication-plan.json')],
                cwd=ROOT,env={**os.environ,'SSS_PYTHON':sys.executable},stdout=out,stderr=err)
        output=Path(plan['output']);result_path=output/'result.json'
        result=read(result_path) if result_path.exists() else {'error':'paper_publication_process_failed'}
        ref=reference(result_path if result_path.exists() else attempt/'publication-stderr.log')
        if code==0 and result.get('status')=='completed':
            return {'status':'published','publication_sha256':result['publication_sha256'],'evidence_ref':ref}
        return {'status':'failed','error':result.get('error','paper_publication_failed'),'committed':(output/'publication.json').exists(),
            'evidence_ref':ref,'repairable':result.get('error')=='capability_store_validation_failed'}


def create_adapter(plan):return PaperCapabilityAdapter(plan)
