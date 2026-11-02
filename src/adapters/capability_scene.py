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

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
from src.adapters.capability_improvement import evidence, read, save, run_improvement, validate
from src.adapters.capability_feedback import CapabilityFeedback
from src.adapters.capability_contract import capability_digest, capability_ref


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
        self.templates = {}
        self.configure_jobs(plan['jobs'])

    def configure_jobs(self,jobs):
        for job in jobs:self.templates[job['id']]=self.freeze_publication_inputs(job)

    def freeze_publication_inputs(self,job):
        raise NotImplementedError('scene_freeze_publication_inputs_required')

    def inspect_run(self,entry,owner):
        raise NotImplementedError('scene_observation_adapter_required')

    def publish(self,job,candidate,attempt,expected_latest):
        raise NotImplementedError('scene_native_publication_required')

    def freeze(self, directory):
        observations=[(entry,self.inspect_run(entry,self.plan['owner'])) for entry in self.plan.get('discovery',[])]
        for entry,observation in observations:
            if observation.get('capability_execution') is True or observation['kind']=='capability_execution':
                trace=observation['trace']
                self.feedback.observe(stage='execution',subject=trace['root'],scope=observation['scope'],
                    status=observation['status'],evidence=observation['evidence'])
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
        if sum(f['status']=='failed' for f in facts)>=2:return 'defer','failed_opportunity_requires_new_evidence'
        return 'start','feedback_allows_trial'

    def record_outcome(self,job,attempt,result,candidate,outcome):
        passed=outcome is not None and outcome['status']=='published'
        key=self.opportunity_key(job)
        refs=[reference(attempt/'result.json')]
        if outcome and outcome.get('evidence_ref'):refs.append(outcome['evidence_ref'])
        scope=job.get('feedback_key',job['id'])
        self.feedback.observe(stage='attempt',subject={'construction_snapshot_sha256':result.get('construction_snapshot_sha256')} if result.get('status')=='deferred' else None,scope=scope,status='passed' if passed else 'unknown' if result.get('status')=='deferred' else 'failed',
            cost=result.get('observed_model_usd'),evidence=refs,opportunity=key)
        if outcome and outcome.get('committed') and not passed and candidate:
            self.feedback.withdraw(capability_ref(candidate['capability']),'committed_followup_failed',refs[-1])
        if passed:
            root=capability_ref(candidate['capability'])
            for ref in candidate['capability']['dependencies']:
                self.feedback.observe(stage='construction',subject=ref,beneficiary=root,scope=scope,
                    status='passed',evidence=refs)
            self.feedback.observe(stage='execution',subject=root,scope=job.get('execution_scope',scope),status='passed',evidence=refs)

    def raw_library(self):
        evidence(self.plan['seed'])
        result = subprocess.run(['node', '--experimental-strip-types',
            'scripts/export-capability-construction-library.mjs', self.plan['store'], self.plan['seed']['path']],
            cwd=ROOT, capture_output=True, text=True, check=True)
        value = json.loads(result.stdout)
        value['source_catalog'] = self.seed_catalog
        return value

    def library(self):
        value=self.feedback.project(self.raw_library())
        if value['snapshot'] is None:raise ValueError('feedback_no_available_capability')
        return value

    def construct(self, task, library, output, parent, feedback):
        context = output.parent/(output.name+'-context'); context.mkdir(mode=0o700)
        save(context/'task.json', task); save(context/'snapshot.json', library['snapshot'])
        # Preserve original leaf descriptions/examples and append verified learned
        # contracts. A model is free to use a primitive, a learned C, or neither.
        save(context/'catalog.json', {'source_catalog':library['source_catalog'],
                                     'learned_and_seed_capabilities':library['catalog'],
                                     'preferred_roots':library.get('selection',{}).get('construction',[]) })
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
