"""Deterministic counterexamples to LLM output approvals; no model calls."""
import json
from pathlib import Path
from src.motif_core.reuse.experience_registry import read,sha,digest,durable,ExperienceRegistry


def structured_output_errors(source,logs):
    if 'JSON.stringify' not in source:return []
    errors=[]
    for i,text in enumerate(logs):
        if not isinstance(text,str) or not text.lstrip().startswith(('{','[')):continue
        try:json.loads(text)
        except (ValueError,TypeError):errors.append('serialized JSON output is incomplete or malformed at log '+str(i))
    return errors


def audit_active_outputs(cfg,root):
    """Revoke contradicted private proof; never rewrite the earlier verdict."""
    root=Path(root);registry=ExperienceRegistry(root/'registry');state=registry.load();rejected=[]
    for entry in state['entries']:
        if entry['kind']!='file_script' or entry['state']!='active':continue
        certfile=registry.root/entry['certificate']['file'];cert=read(certfile)
        if cert.get('status') not in ('certified_file_script_v3','certified_file_script_v4'):continue
        payload=registry.root/entry['payload']
        if sha(certfile)!=entry['certificate']['sha256'] or sha(payload)!=entry['sha256']:
            raise ValueError('original script certificate/payload changed')
        policy=read(payload);source=policy['artifact']['source']
        from src.adapters.file_management.experience_certification import check_motif_certificate
        check_motif_certificate(policy,certfile,entry['sha256'])
        job=Path(cert['candidate_lock_file']).parent
        if not job.resolve().is_relative_to((root/'learning').resolve()):continue
        evidence=[]
        for review in cert['reviews']:
            record_file=Path(review['record_file'])
            if sha(record_file)!=review['record_sha256']:raise ValueError('original script record changed')
            record=read(record_file)
            for receipt in sorted((Path(record['delivery'])/'script-runs').glob('*/receipt.json')):
                observed=read(receipt)
                if observed['public'].get('script_id')!=entry['entry_id']:continue
                children=[read(p) for p in sorted(receipt.parent.glob('call-[0-9][0-9][0-9][0-9].json'))]
                if (observed['invocation_sha256']!=sha(receipt.parent/'invocation.json') or observed['calls_sha256']!=digest(children)):
                    raise ValueError('original script output evidence changed')
                errors=structured_output_errors(source,observed['public']['result'].get('logs',[]))
                if errors:evidence.append({'record_file':str(record_file),'record_sha256':sha(record_file),'receipt':str(receipt),'receipt_sha256':sha(receipt),'errors':errors})
        if not evidence:continue
        errors=list(dict.fromkeys(e for row in evidence for e in row['errors']))
        proof={'format':'sss-file-script-output-counterexample-v1','policy_digest':entry['entry_id'],
            'compiled_sha256':sha(job/'compiled.json'),'original_certificate_sha256':sha(certfile),
            'passed':False,'error':None,'mechanical_errors':errors,'verdict':{'passed':False,'critical_errors':errors,'reason':'Actual serialized output is cut off; reading coverage is not output integrity.'},
            'evidence':evidence,'new_api_requests':0,'old_verdicts_preserved':True}
        file=job/'revocation.json'
        if not file.exists():durable(file,proof,exclusive=True)
        elif read(file)!=proof:raise ValueError('immutable output counterexample changed')
        rejected.append({'entry_id':entry['entry_id'],'proof':str(file),'proof_sha256':sha(file)})
    if rejected:registry.publish(disable=[r['entry_id'] for r in rejected],expected=state['generation'],reason='actual local-output counterexample; old certificates retained; ordinary fallback required')
    return rejected
