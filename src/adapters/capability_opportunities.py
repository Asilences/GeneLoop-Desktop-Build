"""Opt-in reconsideration inside the existing improvement queue.

The host supplies unresolved needs and independent admission. Proposals never
grant execution rights, select validators, or establish actual dependencies.
"""
from __future__ import annotations
import copy
import json
from pathlib import Path
from uuid import uuid4

from .capability_contract import capability_digest, capability_ref, validate_capability_snapshot
from .capability_feedback import file_ref
from .capability_improvement import evidence, save, validate
from .file_lock import exclusive_lock


class OpportunityDiscovery:
    def __init__(self, config, owner):
        self.config, self.owner = copy.deepcopy(config), owner
        self.directory = Path(config['directory']).resolve()/capability_digest(owner)
        self.directory.mkdir(parents=True, exist_ok=True, mode=0o700)
        self.rounds = 0
        self.jobs = {}
        self._context()

    def _context(self):
        context = json.loads(evidence(self.config['context']))
        if (set(context) != {'format','owner','task_scope','allowed_effects','needs'}
                or context['format'] != 'capability_opportunity_context_v1'
                or context['owner'] != self.owner or not isinstance(context['task_scope'],str)
                or not context['task_scope'] or not isinstance(context['needs'],list)
                or not isinstance(context['allowed_effects'],list)
                or any(not isinstance(effect,str) for effect in context['allowed_effects'])):
            raise ValueError('opportunity_context_invalid')
        ids = set()
        for need in context['needs']:
            if (not isinstance(need,dict) or set(need) != {'id','description','status','evidence'}
                    or not isinstance(need['id'],str) or not need['id'] or need['id'] in ids
                    or not isinstance(need['description'],str) or not need['description'].strip()
                    or need['status'] not in ('open','resolved') or not need['evidence']):
                raise ValueError('opportunity_need_invalid')
            ids.add(need['id'])
            for ref in need['evidence']: validate('evidence',ref); evidence(ref)
        return context

    def reconsider(self, previous, library, publication_ref, unresolved, adapter, directory):
        """One event, one proposal call; new jobs return to the original queue."""
        previous = validate_capability_snapshot(previous,self.owner)
        current = validate_capability_snapshot(library['snapshot'],self.owner)
        context = self._context()
        needs = [need for need in context['needs'] if need['status']=='open']
        added = [ref for ref in current['roots'] if ref not in previous['roots']]
        if not added or not needs or self.rounds >= self.config['max_reconsiderations']:
            return []
        for cap in current['capabilities']:
            if cap['certification']!='certified' or cap['lifecycle']=='archived':
                raise ValueError('opportunity_uncertified_snapshot')
        validate('evidence',publication_ref); evidence(publication_ref)
        key = capability_digest({'owner':self.owner,'context':self.config['context']['sha256'],
                                 'before':previous['digest'],'after':current['digest']})
        target = self.directory/key
        with exclusive_lock(self.directory/'writer.lock'):
            if target.exists(): return []  # Includes interrupted/unknown requests.
            target.mkdir(mode=0o700)
            save(target/'claim.json',{'owner':self.owner,'trigger_id':key,
                                     'status':'claimed_no_automatic_replay'})
        self.rounds += 1
        request = {'format':'capability_opportunity_request_v1','trigger_id':key,'owner':self.owner,
            'origin':'capability_update','task_scope':context['task_scope'],
            'allowed_effects':copy.deepcopy(context['allowed_effects']),
            'supporting_evidence':self.config['context'],'needs':needs,
            'previous_snapshot':previous,'capability_snapshot':current,'newly_visible':added,
            'publication_evidence':publication_ref,
            'unresolved_opportunities':[{'id':job['id'],'task':json.loads(evidence(job['task'])),
                'observations':copy.deepcopy(job['observations'])} for job in unresolved
                if job.get('execution_scope')==context['task_scope']],
            'catalog':copy.deepcopy(library.get('source_catalog',{})),
            'max_candidates':self.config['max_candidates']}
        save(target/'request.json',request)
        save(Path(directory)/('opportunity-trigger-'+key[:16]+'.json'),
             {'request':file_ref(target/'request.json'),'ledger_directory':str(target)})
        jobs, decisions = [], []
        try:
            response = adapter.propose_opportunities(request,target/'proposal')
            save(target/'response.json',response)
            if not isinstance(response,dict) or not isinstance(response.get('goals'),list):
                raise ValueError('opportunity_proposal_invalid')
            self._context();evidence(publication_ref)
            known = {row['id'] for row in unresolved} | set(self.jobs)
            for index, proposal in enumerate(response['goals']):
                row = {'index':index,'proposal':proposal,'decision':'rejected','reason':None}
                decisions.append(row)
                try:
                    need = self._validate_goal(proposal,needs,current)
                    goal_id = 'goal-'+capability_digest({'scope':context['task_scope'],'need':need['id'],
                        'need_evidence':sorted(ref['sha256'] for ref in need['evidence']),
                        'goal':' '.join(proposal['proposed_goal'].split())})[:24]
                    row.update(goal_id=goal_id,task_scope=context['task_scope'],origin='capability_update',
                        capability_snapshot=current['digest'],supporting_evidence=need['evidence'],
                        expected_dependencies=proposal['expected_dependencies'],
                        compiled_dependencies=None,actual_dependencies=None,
                        construction_result=None,verification=None)
                    if adapter.library()['snapshot']['digest']!=current['digest']:
                        row.update(decision='pending',reason='capability_snapshot_changed');continue
                    completed=self.directory/('completed-'+goal_id+'.json')
                    prior=json.loads(completed.read_text(encoding='utf-8')) if completed.exists() else None
                    if prior and prior['verification'].get('evidence_ref'):evidence(prior['verification']['evidence_ref'])
                    if goal_id in known or prior and prior['capability'] in current['roots']:
                        row.update(decision='not_selected',reason='duplicate_goal');continue
                    known.add(goal_id)
                    if index >= self.config['max_candidates']:
                        row.update(decision='not_selected',reason='candidate_limit');continue
                    review = adapter.review_opportunity(copy.deepcopy(proposal),copy.deepcopy(request),target)
                    row['host_review'] = review
                    if review.get('decision') != 'accepted':
                        row.update(decision=review.get('decision','pending'),reason=review.get('reason','independent_review_required'))
                        if row['decision'] not in ('pending','rejected','not_selected'):
                            raise ValueError('opportunity_review_invalid')
                        continue
                    review_ref = review['evidence'];validate('evidence',review_ref);evidence(review_ref)
                    job = copy.deepcopy(review['job']);job['id']=goal_id
                    validate('job',job)
                    task = json.loads(evidence(job['task']))
                    contract=task.get('contract')
                    if (not isinstance(contract,dict) or not {'input_schema','output_schema','effects'}<=set(contract)
                            or job.get('execution_scope')!=context['task_scope'] or
                            task.get('instruction')!=proposal['proposed_goal'] or
                            set(task.get('contract',{}).get('effects',[]))-set(context['allowed_effects'])):
                        raise ValueError('opportunity_admission_scope_changed')
                    evidence(job['publication_plan'])
                    for observation in job['observations']:
                        if observation['split']=='heldout':raise ValueError('opportunity_heldout_evidence')
                        evidence(observation['evidence'])
                    if not job['observations'] or not any(o['kind']=='new_requirement' for o in job['observations']):
                        raise ValueError('opportunity_requirement_evidence_required')
                    job['source_evidence'] = [*job.get('source_evidence',[]),*need['evidence'],
                        self.config['context'],file_ref(target/'request.json'),file_ref(target/'response.json'),review_ref]
                    for ref in job['source_evidence']:validate('evidence',ref);evidence(ref)
                    adapter.configure_jobs([job])  # Freeze original scene publication inputs.
                    row.update(decision='selected',reason='host_admitted_with_independent_validation',job=job)
                    self.jobs[goal_id] = target
                    jobs.append(job)
                except (ValueError,KeyError,TypeError) as error:
                    row.update(decision='rejected',reason=str(error))
            save(target/'decisions.json',decisions)
            save(target/'result.json',{'status':response.get('status','completed'),'reason':response.get('reason'),
                'jobs':[job['id'] for job in jobs],
                'proposal_cost':{key:response.get(key) for key in ('model_called','request_ids','observed_model_usd','observed_model_usd_decimal')},
                'creation_benefit':None,'efficiency_conclusion':None})
        except BaseException as error:
            if not (target/'decisions.json').exists():save(target/'decisions.json',decisions)
            save(target/'result.json',{'status':'interrupted' if isinstance(error,(KeyboardInterrupt,SystemExit)) else 'failed',
                'error':str(error),'creation_benefit':None,'efficiency_conclusion':None})
            if isinstance(error,(KeyboardInterrupt,SystemExit)): raise
        return jobs

    @staticmethod
    def _validate_goal(proposal,needs,snapshot):
        if (not isinstance(proposal,dict) or set(proposal)-{'need_id','proposed_goal','expected_dependencies','reason','proposed_interface'}
                or not {'need_id','proposed_goal','expected_dependencies','reason'}<=set(proposal)
                or not isinstance(proposal['proposed_goal'],str) or not proposal['proposed_goal'].strip()
                or not isinstance(proposal['reason'],str) or not proposal['reason'].strip()
                or not isinstance(proposal['expected_dependencies'],list)):
            raise ValueError('opportunity_goal_invalid')
        matches = [need for need in needs if need['id']==proposal['need_id']]
        if len(matches)!=1:raise ValueError('opportunity_need_out_of_scope')
        if any(ref not in snapshot['roots'] for ref in proposal['expected_dependencies']):
            raise ValueError('opportunity_dependency_not_visible')
        return matches[0]

    def record(self, job, attempt, result, candidate=None, outcome=None):
        target = self.jobs.get(job['id'])
        if target is None:return
        record = {'goal_id':job['id'],'decision':'completed' if outcome and outcome.get('status')=='published' else 'attempted',
            'construction_result':file_ref(Path(attempt)/'result.json'),
            'observed_model_usd':result.get('observed_model_usd'),
            'observed_model_usd_decimal':result.get('observed_model_usd_decimal'),
            'compiled_dependencies':None if candidate is None else candidate['capability']['dependencies'],
            'actual_dependencies':None,'verification':outcome if candidate is not None else None,
            'acquisition_result':file_ref(Path(attempt)/'acquisition.json') if (Path(attempt)/'acquisition.json').exists() else None,
            'scope':'Compiled/expected dependencies are not execution observations'}
        if outcome and outcome.get('evidence_ref'):evidence(outcome['evidence_ref'])
        # Optional original Runtime traces, bound to this exact candidate.
        if candidate and outcome and outcome.get('execution_trace_refs'):
            calls=[]
            for ref in outcome['execution_trace_refs']:
                trace=json.loads(evidence(ref))
                if (trace.get('owner')!=self.owner or trace.get('root')!=capability_ref(candidate['capability'])
                        or trace.get('snapshot_sha256')!=candidate['snapshot']['digest'] or trace.get('status')!='succeeded'
                        or trace.get('mode') not in ('validate','execute')):
                    raise ValueError('opportunity_execution_binding_changed')
                if not trace.get('receipts'):raise ValueError('opportunity_execution_receipts_required')
                receipts={row['call_id']:row for row in trace['receipts']}
                roots=[row for row in receipts.values() if row.get('capability')==trace['root'] and row.get('parent_call_id') is None]
                if len(roots)!=1:raise ValueError('opportunity_execution_root_receipt_required')
                pending=[roots[0]];seen=set()
                allowed=[capability_ref(cap) for cap in candidate['snapshot']['capabilities']]
                while pending:
                    parent=pending.pop()
                    if parent['call_id'] in seen:raise ValueError('opportunity_execution_receipt_cycle')
                    seen.add(parent['call_id'])
                    for child_id in parent.get('child_call_ids',[]):
                        child=receipts[child_id]
                        if (child.get('parent_call_id')!=parent['call_id'] or child.get('status')!='succeeded'
                                or child.get('capability') not in allowed):
                            raise ValueError('opportunity_execution_child_binding_changed')
                        calls.append(child['capability']);pending.append(child)
            record['actual_dependencies']=list({capability_digest(ref):ref for ref in calls}.values())
            record['execution_trace_refs']=outcome['execution_trace_refs']
        save(target/('outcome-'+job['id']+'-'+uuid4().hex+'.json'),record)
        if record['decision']=='completed' and candidate:
            with exclusive_lock(self.directory/'writer.lock'):
                path=self.directory/('completed-'+job['id']+'.json')
                if not path.exists():save(path,{'capability':capability_ref(candidate['capability']),'verification':outcome})
