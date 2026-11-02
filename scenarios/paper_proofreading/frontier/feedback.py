"""Trusted final-review feedback after every construction episode is closed.

Use the existing capability withdrawal/projection mechanism. A failed root is
quarantined, never an inferred child. Immutable publications remain untouched.
"""
import json
from pathlib import Path
from src.adapters.capability_feedback import CapabilityFeedback
from src.adapters.capability_improvement import evidence


def record_final_feedback(plan,cell,artifact_ref,scope):
    artifact=json.loads(evidence(artifact_ref))
    if artifact['cell']!=cell:raise ValueError('frontier_feedback_cell_changed')
    published=[v for v in artifact['construction']['outcomes'] if v['status']=='published']
    if not published:return {'cell':cell,'action':'none','reason':'no_published_candidate'}
    if len(published)!=1:raise ValueError('frontier_feedback_root_ambiguous')
    root=published[0]['capability'];cases=artifact['final_cases']
    statuses=[]
    for case in cases:
        quality=case['quality'];checks=quality.get('checks',[])
        # A runtime/transport failure is unknown quality. Never use it as an
        # algorithm counterexample or infer which dependency caused it.
        if 'execution_error' in quality or not checks:
            statuses.append('unknown');continue
        known=all(c.get('status') in ('passed','failed') for c in checks)
        failed=any(c.get('status')=='failed' for c in checks)
        if known and quality.get('passed') is False and failed:statuses.append('failed')
        elif known and quality.get('passed') is True and not failed:statuses.append('passed')
        else:statuses.append('unknown')
    status='failed' if 'failed' in statuses else 'passed' if statuses and all(s=='passed' for s in statuses) else 'unknown'
    feedback=CapabilityFeedback(plan.get('feedback_directory',str(Path(plan['store'])/'feedback')),plan['owner'])
    fact=feedback.observe(stage='execution',subject=root,scope=scope,status=status,cost=None,evidence=[artifact_ref])
    if status=='failed':feedback.withdraw(root,'independent_final_quality_failed',artifact_ref)
    return {'cell':cell,'capability':root,'status':status,'fact_sha256':fact,
            'action':'withdraw_root' if status=='failed' else 'record_only',
            'cost_scope':'Model acquisition already charged to the study episode; execution economics unknown'}
