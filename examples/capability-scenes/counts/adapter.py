"""Second scene conformance adapter: actual subprocesses, synthetic tasks/authority.

It intentionally uses the same controller/proposal/feedback/Store as Source.
This example is not a production Artifact Motif adapter or an efficacy benchmark.
"""
import copy,json,sys,os
from pathlib import Path
from src.adapters.capability_scene import CapabilityImprovementAdapter,ROOT,run_child,reference
from src.adapters.capability_improvement import evidence,read,save
from src.adapters.capability_contract import capability_digest,validate_capability_snapshot
from src.adapters.capability_discovery import read_context


class CountAdapter(CapabilityImprovementAdapter):
    def freeze_publication_inputs(self,job):
        return json.loads(evidence(job['publication_plan']))

    def inspect_run(self,entry,owner):
        if entry['kind']!='count_execution' or entry['role'] not in ('training','validation'):
            raise ValueError('count_observation_scope_invalid')
        run=Path(entry['run']);context=read_context(entry['context'],owner)
        trace=read(run/'trace.json');args=read(run/'args.json');snapshot=validate_capability_snapshot(read(run/'snapshot.json'),owner)
        if trace['owner']!=owner or trace['mode']!='execute' or trace['snapshot_sha256']!=snapshot['digest'] or trace['arguments_sha256']!=capability_digest(args):
            raise ValueError('count_observation_binding_changed')
        if trace['root'] not in snapshot['roots']:raise ValueError('count_observation_root_changed')
        # Scene independently recomputes the result, not a trusted 'passed' flag.
        from collections import Counter
        passed=trace['status']=='succeeded' and trace['result']=={'counts':dict(Counter(r['group'] for r in args['rows']))}
        refs=[entry['context'],*[reference(run/name) for name in ('trace.json','args.json','snapshot.json')]]
        return {'kind':'count_execution','capability_execution':True,'task_id':trace['task_id'],
            'task_fingerprint':capability_digest(args),'status':'passed' if passed else 'failed',
            'context':context,'scope':context['scope'],'evidence':refs,'trace':trace,'role':entry['role']}

    def publish(self,job,candidate,attempt,expected_latest):
        inputs=copy.deepcopy(self.templates[job['id']])
        for label in ('validation','followup'):
            inputs[label]['id']+='-'+job['id']+'-'+attempt.name
            work=attempt/(label+'-workspace');work.mkdir();inputs[label]['workspace']=str(work.resolve())
        output=attempt/'publication'
        plan={**inputs,'owner':self.plan['owner'],'store':self.plan['store'],'candidate':str(attempt/'candidate.json'),
            'expected_latest':expected_latest,'output':str(output)}
        save(attempt/'publication-plan.json',plan)
        with (attempt/'publication-stdout.log').open('w') as out,(attempt/'publication-stderr.log').open('w') as err:
            code=run_child(['node','--experimental-strip-types',str(Path(__file__).with_name('publish.mjs')),str(attempt/'publication-plan.json')],cwd=ROOT,
                env={**os.environ,'SSS_PYTHON':sys.executable},stdout=out,stderr=err)
        result=read(output/'result.json');ref=reference(output/'result.json')
        if code==0 and result['status']=='completed':
            return {'status':'published','publication_sha256':result['publication_sha256'],'evidence_ref':ref}
        return {'status':'failed','error':result.get('error','count_publication_failed'),
            'committed':(output/'publication.json').exists(),'evidence_ref':ref,
            'repairable':result.get('error')=='capability_store_validation_failed'}


def create_adapter(plan):return CountAdapter(plan)
