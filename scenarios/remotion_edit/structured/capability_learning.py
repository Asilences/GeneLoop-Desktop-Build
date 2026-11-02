"""Gap -> existing Source learner -> native certification -> material admission.

Routes are host-authored, evidence-pinned and opt-in. A model describes a gap;
it cannot choose an executable, command, dataset, checker, or budget store.
"""
import json
import os
from pathlib import Path
import subprocess
import sys
from src.adapters.capability_scene import ROOT,reference,run_child
from src.adapters.capability_improvement import evidence,read,save
from src.adapters.capability_contract import capability_digest
from src.adapters.file_lock import exclusive_lock
from scenarios.remotion_edit.structured.learn_programs import collect

FILES=('scenarios/remotion_edit/structured/learn_programs.py',
       'scenarios/remotion_edit/structured/certify_programs.py')


def acquire_source(adapter,job,result,attempt):
    gap=result.get('construction_gap') or {}
    routes_ref=adapter.plan.get('learning_routes')
    if gap.get('reason')!='missing_primitive' or routes_ref is None:
        return {'status':'deferred','reason':'no_admitted_source_learning_route'}
    config=json.loads(evidence(routes_ref))
    if config.get('owner')!=adapter.plan['owner'] or config.get('format')!='source_learning_routes_v1':
        raise ValueError('source_learning_routes_invalid')
    matches=[r for r in config['routes'] if r['scope']==job.get('execution_scope')]
    if len(matches)!=1:
        return {'status':'deferred','reason':'source_learning_route_ambiguous_or_absent'}
    route=matches[0]
    if route.get('backend')!='source_program' or not route.get('runs'):
        return {'status':'deferred','reason':'source_learning_evidence_missing'}
    refs=[routes_ref]
    for row in route['runs']:
        if row.get('role')!='training':raise ValueError('source_learning_training_only')
        # Reuse the original collector and bind ALL inputs it consumes, not
        # just a supplied assertion that a task was successful.
        from scenarios.remotion_edit.structured.capability_observations import inspect_run
        observed=inspect_run({'kind':'native_source','run':row['run'],'role':'training','context':row['context']},adapter.plan['owner'])
        if observed['scope']!=job.get('execution_scope'):raise ValueError('source_learning_scope_changed')
        expected=row['evidence']
        for ref in expected:evidence(ref)
        if any(ref not in expected for ref in observed['evidence']):raise ValueError('source_learning_unpinned_evidence')
        refs.extend(expected)
        collect(Path(row['run']))
    refs.extend(reference(ROOT/name) for name in FILES)
    ledger=Path(adapter.plan['ledger_root'])
    if not all((ledger/name).is_file() for name in ('budget-checkpoint.json','cost-ledger.jsonl')):
        raise ValueError('source_existing_cumulative_ledger_required')
    key=capability_digest({'route':route,'evidence':refs})
    directory=adapter.materials.directory/'acquisitions'/key
    directory.mkdir(parents=True,exist_ok=True,mode=0o700)
    with exclusive_lock(directory/'.lock'):
        # An interrupted learner may have consumed money or made artifacts.
        # Never silently replay it; retain the original ledger and attempt.
        if (directory/'request.json').exists():
            return {'status':'deferred','reason':'source_learning_already_attempted_review_or_new_evidence_required',
                    'request':reference(directory/'request.json')}
        save(directory/'request.json',{'job':job['id'],'opportunity':adapter.opportunity_key(job),
            'gap':gap,'gap_evidence':reference(attempt/'result.json'),'route':route,'evidence':refs,
            'model':'deepseek-flash','reasoning_effort':'off','max_output_tokens':393216,
            'cap_usd':None,'request_limit':None,'ledger_root':adapter.plan['ledger_root']})
        commands=[
            [sys.executable,str(ROOT/FILES[0]),*[a for r in route['runs'] for a in ('--run',r['run'])],
             '--output',str(directory/'learn'),'--ledger-root',adapter.plan['ledger_root'],
             '--experiment-id',adapter.plan['id'],
             '--max-output-tokens','393216','--call-model'],
            [sys.executable,str(ROOT/FILES[1]),'--library',str(directory/'learn/candidate-library.json'),
             '--output',str(directory/'certify')]]
        try:
            for phase,command in zip(('learn','certify'),commands):
                for ref in refs:evidence(ref)
                with (directory/(phase+'-stdout.log')).open('w') as out,(directory/(phase+'-stderr.log')).open('w') as err:
                    with exclusive_lock(ledger/'capability-proposal.lock'):
                        code=run_child(command,cwd=ROOT,env={**os.environ,'SSS_PYTHON':sys.executable},stdout=out,stderr=err)
                if code:raise ValueError('source_'+phase+'_process_failed')
            library=reference(directory/'certify/library.json')
            # The same native decoder used at execution must accept it before
            # registration. Empty/rejected results do not wake the Builder.
            probe=subprocess.run(['node','scripts/run-source-capability.mjs','--catalog','--library',library['path'],
                '--owner',adapter.plan['owner']],cwd=ROOT,capture_output=True,text=True,check=True)
            catalog=json.loads(probe.stdout)
            if not catalog['capabilities']:raise ValueError('source_learning_no_certified_material')
            for ref in refs:evidence(ref)
            refs += [reference(directory/'request.json'),reference(directory/'learn/learning-summary.json')]
            refs += [reference(p) for p in sorted((directory/'certify').glob('*/verification.json'))]
            admission=adapter.materials.register(backend='source_program',library=library,refs=refs,
                acquisition_key=key,opportunity=adapter.opportunity_key(job))
            outcome={'status':'registered','material':admission,'learning_cost_evidence':reference(directory/'learn/learning-summary.json'),
                     'benefit':None}
        except Exception as error:
            outcome={'status':'deferred','reason':str(error),'request':reference(directory/'request.json'),'benefit':None}
        save(directory/'result.json',outcome)
        return outcome
