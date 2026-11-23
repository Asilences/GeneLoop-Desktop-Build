"""Verify file-management programs and Motifs before experience admission."""

from __future__ import annotations

import json
from pathlib import Path

from src.motif_core.reuse.experience_registry import read, sha


def check_script_certificate(program, path, raw_sha):
    cert = read(path)
    if cert.get('status') not in ('certified', 'certified_v2') or cert.get('holdout_used') is not False:
        raise ValueError('independent certificate required; holdout evidence prohibited')
    if not any(r.get('script_digest') == program['script_digest'] and r.get('sha256') == raw_sha
               for r in cert.get('scripts', [])):
        raise ValueError('certificate does not bind original candidate bytes')
    training = {r['task_fingerprint'] for r in program['training']}
    eligible = [r for r in cert.get('reviews', []) if r.get('actual_candidate_execution', True)]
    reviews = [r for r in eligible if
               (r.get('script_digest') == program['script_digest'] if 'script_digest' in r else
                r.get('workflow_id', r.get('profile_id', '')).split(':')[0] == program['workflow_id'])]
    # Historical v1 reviews label task family in task_id, not workflow_id.
    if not reviews:
        reviews = [r for r in eligible if program['workflow_id'] in r.get('task_id', '')]
    if len(reviews) < 2 or len({r['task_fingerprint'] for r in reviews}) != len(reviews):
        raise ValueError('at least two independent certification materials required')
    for r in reviews:
        if r['task_fingerprint'] in training or r.get('role', 'certify') != 'certify':
            raise ValueError('training/certification/holdout overlap')
        p = Path(r['outcome_file'])
        if sha(p) != r['outcome_sha256']:
            raise ValueError('certification outcome changed')
        outcome = read(p)
        if outcome['role'] != 'certify' or not outcome['acceptance']['passed'] or not outcome['receipt_verified']:
            raise ValueError('failed independent candidate execution')
        if outcome['run']['upstream_requests'] or outcome.get('acceptance_repairs', 0):
            raise ValueError('ordinary repair cannot certify a failed whole program')
    return cert


def check_motif_certificate(policy, path, raw_sha):
    """New continuous admission needs native graph proof and independent actual use."""
    cert = read(path)
    if policy.get('format')=='sss-file-source-program-v1':
        from ..file_script_learning import verify_script_certificate
        return verify_script_certificate(policy,path,raw_sha)
    if cert.get('format')=='sss-management-seed-attestation-v1':
        from ..management_seed import validate_certificate
        return validate_certificate(policy,path,raw_sha)
    v2=policy.get('format')=='sss-operation-graph-v2';v3=policy.get('format')=='sss-operation-flow-v3'
    if (cert.get('status') != ('certified_motif_v3' if v3 else 'certified_motif_v2' if v2 else 'certified_motif_v1') or cert.get('holdout_used') is not False
            or cert.get('policy_digest') != policy['policy_digest'] or cert.get('payload_sha256') != raw_sha
            or cert.get('quality_and_permission_required') is not True):
        raise ValueError('independent actual Motif certificate required')
    if v2 and (cert.get('certification_contract')!='sss-operation-certification-v2' or policy['artifact'].get('certification_contract')!='sss-operation-certification-v2'):
        raise ValueError('versioned operation certification required')
    if v3 and (cert.get('certification_contract')!='sss-operation-certification-v3' or policy['artifact'].get('certification_contract')!='sss-operation-certification-v3'):
        raise ValueError('versioned control-flow certification required')
    if sha(cert['candidate_lock_file']) != cert['candidate_lock_sha256']:
        raise ValueError('Motif candidate lock changed')
    training = set(policy['artifact']['source_task_fingerprints'])
    reviews = [cert['native_review'], *cert.get('reviews', [])]
    if len(cert.get('reviews', [])) != 2 or len({r['task_fingerprint'] for r in reviews}) != len(reviews):
        raise ValueError('new native witness and two independent Motif executions required')
    for review in reviews:
        if review['task_fingerprint'] in training or sha(review['record_file']) != review['record_sha256']:
            raise ValueError('Motif evidence overlap or mutation')
        record = read(review['record_file'])
        if (record['role'] != review['role'] or not record['accepted'] or not record['lifecycle_verified']
                or record['provider_mode'] != 'real' or record['metrics'].get('acceptance_repairs')
                or record.get('observed_usage_complete') is False):
            raise ValueError('failed or repaired Motif certification')
        if review['role'] == 'candidate_certification' and (record['policy_digest'] != policy['policy_digest']
                or record['verified_motif_batches'] < 1 or record['deferred']):
            raise ValueError('candidate did not actually execute its Motif')
        if (v2 or v3) and review['role']=='candidate_certification':
            if review.get('completion_count',0)<1 or sha(Path(record['run_dir'])/'experience-audit.jsonl')!=review.get('audit_sha256'):raise ValueError('repeated operation proof changed')
    if policy.get('format')=='sss-management-program-v1':
        from ..management_legacy import verify_program_delivery
        if cert.get('certification_contract')!='sss-management-program-certification-v1' or policy['artifact'].get('certification_contract')!=cert['certification_contract']:
            raise ValueError('current bounded program certification required')
        if sha(cert['native_program_proof_file'])!=cert['native_program_proof_sha256']:raise ValueError('native program proof changed')
        if policy['artifact'].get('delivery_contract')!='sss-exact-management-program-delivery-v1' or sha(cert['native_program_delivery_file'])!=cert['native_program_delivery_sha256']:raise ValueError('exact program delivery proof required')
        for review in reviews:verify_program_delivery(policy['artifact']['recipe'],read(review['record_file']))
        for review in cert['reviews']:
            record=read(review['record_file']);audit=Path(record['run_dir'])/'experience-audit.jsonl'
            if sha(audit)!=review.get('audit_sha256'):raise ValueError('program actual audit changed')
            completions=[json.loads(l) for l in audit.read_text().splitlines() if json.loads(l).get('kind')=='management_program_complete']
            if len(completions)!=1 or completions[0]['entry_id']!=policy['policy_digest'] or completions[0]['copy_stages']!=sum(s['op']=='copy_map' for s in policy['artifact']['recipe']['steps']):
                raise ValueError('complete actual program execution required')
    legacy=policy.get('artifact',{}).get('legacy_adapter',{})
    if legacy.get('family')=='reentry':
        for review in cert['reviews']:
            if review.get('completion_count',0)!=2:raise ValueError('two independently model-selected reading episodes required')
    return cert
