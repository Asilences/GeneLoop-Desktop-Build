"""Source scene adapter; discovery, proposal and feedback use the common engine."""
from __future__ import annotations
import argparse,copy,hashlib,json,os,subprocess,sys,signal
from pathlib import Path
ROOT=Path(__file__).resolve().parents[3]
sys.path.insert(0,str(ROOT))
from src.adapters.capability_improvement import evidence,read,save,run_improvement,validate
from src.adapters.capability_scene import CapabilityImprovementAdapter,reference,run_child

class SourceImprovementAdapter(CapabilityImprovementAdapter):
    withdrawal_reasons=CapabilityImprovementAdapter.withdrawal_reasons|{'source_capability_leaf_changed'}
    def freeze_publication_inputs(self,job):
        template=json.loads(evidence(job['publication_plan']))
        return {key:read(template[key]) for key in ('validation_manifest','validation_args','validation_specification',
            'followup_manifest','followup_args','followup_specification')}

    def inspect_run(self,entry,owner):
        from scenarios.remotion_edit.structured.capability_observations import inspect_run
        return inspect_run(entry,owner)

    def publish(self, job, candidate, attempt, expected_latest):
        inputs = copy.deepcopy(self.templates[job['id']])
        context = attempt/'publication-inputs'; context.mkdir(mode=0o700)
        plan = dict(owner=self.plan['owner'], store=self.plan['store'],
                    candidate=str(attempt/'candidate.json'), expected_latest=expected_latest,
                    output=str(attempt/'publication'))
        # Every repair gets distinct workspaces/task identities. Never replay a
        # failed render in an old workspace or delete previous attempt evidence.
        for key, value in inputs.items():
            if key.endswith('_manifest'):
                value['task_id'] += '-'+job['id']+'-'+attempt.name
                source = Path(value['workspace']).resolve()
                work = context/(key+'-workspace'); work.mkdir(mode=0o700)
                (work/'inputs').mkdir(mode=0o700)
                import shutil
                for item in value['inputs']:
                    original = Path(item['path']).resolve()
                    if not original.is_relative_to(source):
                        raise ValueError('improvement_input_outside_task')
                    raw = original.read_bytes()
                    if hashlib.sha256(raw).hexdigest() != item['sha256']:
                        raise ValueError('improvement_source_input_changed')
                    target = work/'inputs'/item['name']
                    if target.parent != work/'inputs':
                        raise ValueError('improvement_input_name_invalid')
                    shutil.copyfile(original,target)
                    item['path'] = str(target)
                value['workspace'] = str(work)
            path = context/(key+'.json'); save(path,value); plan[key] = str(path)
        save(context/'plan.json',plan)
        env = {**os.environ,'SSS_PYTHON':sys.executable}
        with (context/'stdout.json').open('w') as out, (context/'stderr.log').open('w') as err:
            returncode = run_child(['node','--experimental-strip-types','scripts/complete-source-capability-loop.mjs',
                                      str(context/'plan.json')],cwd=ROOT,env=env,stdout=out,stderr=err)
        directory = Path(plan['output'])
        result = read(directory/'result.json') if (directory/'result.json').exists() else {'error':'publication_process_failed'}
        committed = (directory/'publication.json').exists()
        result_ref = reference(directory/'result.json') if (directory/'result.json').exists() else reference(context/'stderr.log')
        if returncode == 0 and result.get('status') == 'completed' and result.get('followup_passed') is True:
            return {'status':'published','publication_sha256':result['publication_sha256'],'evidence_ref':result_ref}
        feedback = None
        if (directory/'validation/validation.json').exists():
            try: feedback = read(directory/'validation/validation.json')
            except json.JSONDecodeError: pass
        return {'status':'failed','error':result.get('error','publication_process_failed'),
                'committed':committed,'evidence_ref':result_ref,'feedback':feedback,
                'repairable':result.get('error') in ('loop_independent_validation_failed','capability_store_validation_failed','loop_video_result_missing')}


def main():
    def interrupted(signum, frame):
        raise KeyboardInterrupt('improvement_interrupted')
    signal.signal(signal.SIGTERM, interrupted)
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--plan',type=Path,required=True)
    parser.add_argument('--call-model',action='store_true')
    args=parser.parse_args(); plan=read(args.plan); validate('plan',plan)
    if not Path(plan['output']).resolve().is_relative_to(ROOT/'.local'):
        parser.error('raw improvement artifacts must remain in private project .local')
    adapter=SourceImprovementAdapter(plan)
    result=run_improvement(plan,adapter,execute=args.call_model)
    print(json.dumps(result,ensure_ascii=False))
    if result['status'] not in ('completed','preview'):
        raise SystemExit(1)

if __name__=='__main__':main()
