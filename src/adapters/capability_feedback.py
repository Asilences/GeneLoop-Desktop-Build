"""Trusted offline feedback, selection and withdrawal; no model or runtime authority.

Facts reference immutable evidence. Unknown benefit/cost is not zero. Selection
only orders host-admitted alternatives; similarity of schemas is not equivalence.
"""
from __future__ import annotations
import copy
import hashlib
import json
import math
import os
from contextlib import contextmanager
from pathlib import Path
from uuid import uuid4
from .capability_contract import capability_digest, capability_ref, create_capability_snapshot, validate_capability_snapshot
from .file_lock import exclusive_lock


def file_ref(path):
    return {'path':str(Path(path).resolve()),'sha256':hashlib.sha256(Path(path).read_bytes()).hexdigest()}


def verify(ref):
    raw=Path(ref['path']).read_bytes()
    if hashlib.sha256(raw).hexdigest()!=ref['sha256']:raise ValueError('feedback_evidence_changed')
    return raw


class CapabilityFeedback:
    def __init__(self,directory,owner):
        self.owner=owner
        self.directory=Path(directory).resolve()/hashlib.sha256(owner.encode()).hexdigest()
        self.directory.mkdir(parents=True,exist_ok=True,mode=0o700)
        self.path=self.directory/'feedback.json'

    def read(self):
        if not self.path.exists():return {'format':'capability_feedback_v1','owner':self.owner,'facts':{},'blocked':{},'archived':[],'history':[]}
        value=json.loads(self.path.read_text(encoding='utf-8'))
        if value.get('format')!='capability_feedback_v1' or value.get('owner')!=self.owner:raise ValueError('feedback_owner_changed')
        for fact in value['facts'].values():
            for ref in fact['evidence']:verify(ref)
        return value

    @contextmanager
    def update(self):
        with exclusive_lock(self.directory/'writer.lock'):
            state=self.read()
            yield state
            temp=self.directory/('.state-'+uuid4().hex)
            try:
                with temp.open('x',encoding='utf-8') as f:
                    os.chmod(temp,0o600);json.dump(state,f,ensure_ascii=False,allow_nan=False);f.flush();os.fsync(f.fileno())
                os.replace(temp,self.path)
            finally:
                if temp.exists():temp.unlink()

    def observe(self,*,stage,subject,beneficiary=None,scope,status,cost=None,evidence,opportunity=None):
        if stage not in ('execution','construction','attempt') or status not in ('passed','failed','unknown'):raise ValueError('feedback_fact_invalid')
        if cost is not None and (type(cost) not in (int,float) or not math.isfinite(cost) or cost<0):raise ValueError('feedback_cost_invalid')
        if not scope or not evidence:raise ValueError('feedback_scope_and_evidence_required')
        for ref in evidence:verify(ref)
        fact={'stage':stage,'subject':subject,'beneficiary':beneficiary,'scope':scope,'status':status,
              'cost':cost,'evidence':evidence,'opportunity':opportunity,'benefit':None}
        identity=capability_digest(fact)
        with self.update() as state:state['facts'][identity]=fact
        return identity

    def withdraw(self,ref,reason,evidence):
        verify(evidence)
        with self.update() as state:
            state['blocked'][ref['id']]={'capability':ref,'reason':reason,'evidence':evidence}
            state['history'].append({'action':'withdraw','capability':ref,'reason':reason,'evidence':evidence})

    def recover(self,ref,revalidate_and_publish):
        # Trusted host callback must run the existing independent validation and
        # Store publish/load path with this new task ID, not return an old record.
        state=self.read();blocked=state['blocked'].get(ref['id'])
        if not blocked or blocked['capability']!=ref:raise ValueError('feedback_not_withdrawn')
        task_id='recovery-'+uuid4().hex
        publication=revalidate_and_publish(task_id)
        if publication['publication'].get('task_id')!=task_id:raise ValueError('feedback_fresh_validation_required')
        if publication['publication']['root']!=ref or publication['snapshot']['owner']!=self.owner:raise ValueError('feedback_recovery_binding_changed')
        with self.update() as state:
            if state['blocked'].get(ref['id'])!=blocked:raise ValueError('feedback_withdrawal_changed')
            del state['blocked'][ref['id']]
            state['history'].append({'action':'recover','capability':ref,'publication_sha256':publication['publication_sha256'],'task_id':task_id})

    def archive(self,ref,replacement,library):
        if ref==replacement:raise ValueError('feedback_replacement_must_differ')
        snapshot=validate_capability_snapshot(library['snapshot'],self.owner)
        allowed={r['id']:r for r in snapshot['roots']}
        if allowed.get(ref['id'])!=ref or allowed.get(replacement['id'])!=replacement:raise ValueError('feedback_replacement_not_available')
        caps={c['id']:c for c in snapshot['capabilities']}
        if caps[ref['id']]['contract']!=caps[replacement['id']]['contract']:raise ValueError('feedback_replacement_contract_changed')
        state=self.read()
        # Host explicitly proposes replacement; independent success for a common
        # task/rubric scope is required. No automatic claim of universal dominance.
        scopes=lambda r:{f['scope'] for f in state['facts'].values() if f['stage']=='execution' and f['status']=='passed' and f['subject']==r}
        if not scopes(ref).intersection(scopes(replacement)):raise ValueError('feedback_replacement_evidence_required')
        with self.update() as state:
            if ref['id'] not in state['archived']:state['archived'].append(ref['id'])
            state['history'].append({'action':'archive_execution_only','capability':ref,'replacement':replacement})

    def project(self,library):
        snapshot=validate_capability_snapshot(library['snapshot'],self.owner);state=self.read()
        caps={c['id']:c for c in snapshot['capabilities']}
        blocked={key for key,value in state['blocked'].items() if key in caps and capability_ref(caps[key])==value['capability']}
        for value in state['blocked'].values():verify(value['evidence'])
        affected=set(blocked)
        while True:
            extra={c['id'] for c in caps.values() if any(d['id'] in affected for d in c['dependencies'])}
            if extra<=affected:break
            affected.update(extra)
        roots=[r for r in snapshot['roots'] if r['id'] not in affected]
        closure={}
        def collect(ref):
            if ref['id'] in closure:return
            cap=caps[ref['id']];closure[ref['id']]=cap
            for child in cap['dependencies']:collect(child)
        for ref in roots:collect(ref)
        result=copy.deepcopy(library)
        result['recovery_queue']=[{'capability':capability_ref(caps[key]),'action':'revalidate_or_rebuild',
                                   'reason':'withdrawn_dependency' if key not in blocked else state['blocked'][key]['reason']} for key in sorted(affected)]
        # Persist even when all roots are unavailable, so recovery is actionable.
        target=self.directory/('recovery-'+uuid4().hex)
        try:
            with target.open('x',encoding='utf-8') as f:
                os.chmod(target,0o600);json.dump(result['recovery_queue'],f,ensure_ascii=False);f.flush();os.fsync(f.fileno())
            os.replace(target,self.directory/'recovery-queue.json')
        finally:
            if target.exists():target.unlink()
        result['snapshot']=create_capability_snapshot(self.owner,roots,list(closure.values())) if roots else None
        result['catalog']=[row for row in library.get('catalog',[]) if row['capability'] in roots]
        result['feedback_sha256']=capability_digest(state)
        result['selection']={'construction':self.order(roots,'construction',None,state),
                             'execution':self.order(roots,'execution',None,state)}
        return result

    def order(self,roots,stage,scope=None,state=None):
        state=self.read() if state is None else state
        def score(ref):
            facts=[f for f in state['facts'].values() if f['subject']==ref]
            creation=sum(f['stage']=='construction' and f['status']=='passed' for f in facts)
            execution=[f for f in facts if f['stage']=='execution' and (scope is None or f['scope']==scope)]
            passed=sum(f['status']=='passed' for f in execution)
            failed=sum(f['status']=='failed' for f in execution)
            # Cross-task costs are not compared. Only an explicit common scope
            # permits observed average model-cost ordering; other costs unknown.
            costs=[f['cost'] for f in execution if f['status']=='passed'] if scope is not None else []
            mean=sum(costs)/len(costs) if costs and all(c is not None for c in costs) else math.inf
            return (-creation,failed,-passed,mean) if stage=='construction' else (failed,-bool(passed),mean,-passed)
        eligible=[r for r in roots if stage!='execution' or r['id'] not in state['archived']]
        return sorted(eligible,key=lambda r:(score(r),r['id']))

    def select_execution(self,library,eligible,scope):
        projected=self.project(library)
        if projected['snapshot'] is None:raise ValueError('feedback_no_available_capability')
        available=projected['snapshot']['roots']
        if any(ref not in library['snapshot']['roots'] for ref in eligible):raise ValueError('feedback_alternative_not_admitted')
        ranked=self.order([ref for ref in eligible if ref in available],'execution',scope)
        if not ranked:raise ValueError('feedback_no_available_capability')
        return ranked[0],projected

    def prioritize(self,jobs):
        state=self.read()
        def score(job):
            facts=[f for f in state['facts'].values() if f['stage']=='attempt' and f['scope']==job.get('feedback_key',job['id'])]
            failed=sum(f['status']=='failed' for f in facts)
            known=sum(f['cost'] for f in facts if f['cost'] is not None)
            return (failed,known)
        return sorted(jobs,key=score)
