"""Source adapter for the common offline improvement coordinator; preview by default."""
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

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT))
from src.adapters.capability_improvement import evidence, read, save, run_improvement, validate


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


class SourceImprovementAdapter:
    def __init__(self, plan):
        self.plan = copy.deepcopy(plan)
        self.seed = json.loads(evidence(plan['seed']))
        self.seed_catalog = json.loads(evidence(plan['seed_catalog']))
        if self.seed['owner'] != plan['owner']:
            raise ValueError('improvement_seed_owner_changed')
        self.templates = {}
        # Freeze every validation/followup input before the first model request.
        for job in plan['jobs']:
            template = json.loads(evidence(job['publication_plan']))
            inputs = {}
            for key in ('validation_manifest', 'validation_args', 'validation_specification',
                        'followup_manifest', 'followup_args', 'followup_specification'):
                inputs[key] = read(template[key])
            self.templates[job['id']] = inputs

    def freeze(self, directory):
        save(Path(directory)/'source-context.json', {'seed':self.seed,
            'source_catalog':self.seed_catalog, 'publication_inputs':self.templates})

    def library(self):
        evidence(self.plan['seed'])
        result = subprocess.run(['node', '--experimental-strip-types',
            'scripts/export-capability-construction-library.mjs', self.plan['store'], self.plan['seed']['path']],
            cwd=ROOT, capture_output=True, text=True, check=True)
        value = json.loads(result.stdout)
        value['source_catalog'] = self.seed_catalog
        return value

    def construct(self, task, library, output, parent, feedback):
        context = output.parent/(output.name+'-context'); context.mkdir(mode=0o700)
        save(context/'task.json', task); save(context/'snapshot.json', library['snapshot'])
        # Preserve original leaf descriptions/examples and append verified learned
        # contracts. A model is free to use a primitive, a learned C, or neither.
        save(context/'catalog.json', {'source_catalog':library['source_catalog'],
                                     'learned_and_seed_capabilities':library['catalog']})
        args = [sys.executable, str(ROOT/'scenarios/remotion_edit/structured/run_capability_loop.py'),
                '--task',str(context/'task.json'),'--catalog',str(context/'catalog.json'),
                '--snapshot',str(context/'snapshot.json'),'--output',str(output),
                '--ledger-root',self.plan['ledger_root'],'--call-model']
        if parent:
            save(context/'feedback.json', feedback)
            args += ['--repair-from',str(parent),'--feedback',str(context/'feedback.json')]
        with (context/'stdout.json').open('w') as out, (context/'stderr.log').open('w') as err:
            run_child(args, cwd=ROOT, stdout=out, stderr=err)
        return read(output/'result.json')

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
                'committed':committed,'evidence_ref':result_ref,'feedback':feedback}


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
    if args.call_model:
        adapter=SourceImprovementAdapter(plan)
    else:
        adapter=None
    result=run_improvement(plan,adapter,execute=args.call_model)
    print(json.dumps(result,ensure_ascii=False))
    if result['status'] not in ('completed','preview'):
        raise SystemExit(1)

if __name__=='__main__':main()
