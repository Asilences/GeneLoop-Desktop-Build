"""Frontier experiment adapter on the existing improvement controller."""
from __future__ import annotations
import copy,json,os,subprocess,sys
from pathlib import Path
from src.adapters.capability_scene import CapabilityImprovementAdapter,ROOT,reference,run_child
from src.adapters.capability_improvement import evidence,read,save
from src.adapters.capability_contract import capability_digest
from src.adapters.capability_proposal import write
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
        return value

    def construct(self,task,library,output,parent,feedback):
        result=propose(task=task,library=library,output=output,gate=self.gate,parent=parent,feedback=feedback,
                       owner_id=self.plan['id']+'/'+str(output.relative_to(Path(self.plan['output']))))
        if result.get('program_request'):
            program=read(output/'program.json');template=next(iter(self.templates.values()))
            try:
                result['native_library']=learn(program,template['native_cases'][program['mode']],output/'native',
                    reference(output/'answer.txt'),large_output=True)
            except Exception as error:
                diagnostics={'native_error':str(error)}
                for p in (output/'native').glob('**/certification.json'):diagnostics['certification']=read(p)
                for p in (output/'native').glob('**/source-stderr.txt'):
                    if p.read_text().strip():diagnostics[p.parent.name+'_stderr']=p.read_text()[-6000:]
                result.update(status='failed',error='frontier_native_material_rejected',diagnostics=diagnostics)
            write(output/'result.json',result)
        return result

    def acquire(self,job,result,attempt):
        if not result.get('native_library'):return {'status':'deferred','reason':'frontier_no_certified_material'}
        refs=[reference(attempt/'answer.txt'),reference(attempt/'native/certification.json'),job['publication_plan']]
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
        for label in ('validation','followup'):
            p=directory/label/'validation.json'
            if p.exists() and not read(p)['passed']:feedback=read(p);break
        return {'status':'failed','error':result.get('error','frontier_publication_failed'),
            'committed':(directory/'publication.json').exists(),'evidence_ref':ref,
            'repairable':result.get('error')=='capability_store_validation_failed','feedback':feedback}


def create_adapter(plan):return FrontierAdapter(plan)
