"""Separate functional evidence from explicitly authorized bounded cost estimates."""
import math
from pathlib import Path
from src.motif_core.reuse.experience_registry import read,sha,digest

POLICY='sss-file-conservative-cost-v1'

def ledger_evidence(path,requests,cost,observed,policy=None):
    rows=[__import__('json').loads(s) for s in Path(path).read_text().splitlines()]
    paid=[r for r in rows if r.get('kind') not in ('budget_denied','files_api')]
    if len(paid)!=requests:raise ValueError('cost evidence missing paid requests')
    amount=0;uncertain=[]
    for r in paid:
        value=r.get('observed_peak_usd')
        if value is None:
            u=r.get('response_usage',{})
            # This authorization covers incoherent counters, not absent responses,
            # missing usage, network errors or an unbounded/unrecorded charge.
            if (policy!=POLICY or r.get('response_status')!=200
                or any(type(u.get(k)) is not int or u[k]<0 for k in ('prompt_tokens','completion_tokens','total_tokens'))
                or u['prompt_tokens']+u['completion_tokens']==u['total_tokens']):
                raise ValueError('unobserved cost is outside authorized counter-inconsistency policy')
            value=r.get('reserved_upper_usd')
            uncertain.append({'request_id':r.get('request_id'),'response_status':200,'raw_usage':u,'reserved_upper_usd':value})
        if type(value) not in (int,float) or not math.isfinite(value) or value<0:
            raise ValueError('cost evidence has no finite conservative amount')
        amount+=value
    if abs(amount-cost)>1e-6:raise ValueError('cost evidence does not reconcile original charged amount')
    if not observed and not uncertain:raise ValueError('usage uncertainty is not explained by the authorized policy')
    return {'format':'sss-file-cost-evidence-v1','policy':policy or 'strict_observed',
            'ledger_sha256':sha(path),'requests':requests,'reference_or_upper_usd':cost,
            'observed_usage_complete':observed,'counter_inconsistencies':uncertain,
            'provider_invoice_verified':False,'raw_counters_modified':False}

def record_evidence(record,policy=None):
    if not record.get('accounting_complete'):raise ValueError('incomplete original provider accounting')
    if policy==POLICY:
        enrollment=read(Path(record['origin'])/'enrollment.json')
        if enrollment['config'].get('accounting_policy')!=POLICY:
            raise ValueError('original task did not authorize bounded counter accounting')
    return ledger_evidence(Path(record['run_dir'])/'cost-ledger.jsonl',record['upstream_requests'],
                           record['cost_usd'],record.get('observed_usage_complete') is True,policy)

def original_policy(record):
    if record.get('observed_usage_complete') is not False:return None
    return read(Path(record['origin'])/'enrollment.json')['config'].get('accounting_policy')
