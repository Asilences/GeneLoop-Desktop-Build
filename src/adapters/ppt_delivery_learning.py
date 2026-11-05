"""Learn narrowly scoped font repairs from immutable failed and delivered exports."""
from pathlib import Path
import hashlib
import json
import re


def learn_delivery_fonts(output, store, infos, deliveries):
    output, store = Path(output), Path(store)
    pages = []
    for info in infos.values():
        if info['state'].get('status') != 'completed' or info['state'].get('failure'):
            continue
        directory = Path(info['task_dir']) / 'ppt-delivery-receipts'
        if not directory.is_dir():
            continue
        for path in sorted(directory.glob('*.json')):
            if not re.fullmatch(r'[a-f0-9]{64}\.json', path.name):
                continue
            if path.is_symlink() or path.resolve() != path.absolute() or path.stat().st_nlink != 1:
                raise ValueError('font_learning_receipt_changed')
            raw = path.read_bytes()
            receipt = json.loads(raw)
            if receipt.get('mechanical_status') == 'passed' and not any(
                    item.get('path', '').endswith('.pptx') and item.get('sha256') in deliveries.get(info['task_id'], set())
                    for item in receipt.get('artifacts', [])):
                continue
            for page in receipt.get('page_receipts', []):
                if page.get('font_independent_signature'):
                    pages.append((info, path, hashlib.sha256(raw).hexdigest(), receipt, page))
    rules = {}
    for info, failed_path, failed_sha, failed, before in pages:
        families = {finding.get('font_family') for finding in before.get('preflight', {}).get('findings', [])
                    if finding['rule'] == 'missing_glyphs' and finding.get('font_family')}
        for other, passed_path, passed_sha, passed, after in pages:
            if info['task_id'] != other['task_id'] or failed_path == passed_path:
                continue
            if (passed.get('mechanical_status') != 'passed' or passed.get('findings') or
                    failed.get('dependencies', {}).get('environment') != passed.get('dependencies', {}).get('environment') or
                    before['font_independent_signature'] != after['font_independent_signature']):
                continue
            targets = {name.rsplit(':', 1)[0] for name in after.get('preflight', {}).get('fonts', {})}
            if len(targets) != 1:
                continue
            target = targets.pop()
            if any(character in target for character in ';:{}<>\r\n\\'):
                continue
            for family in sorted(families):
                if family == target:
                    continue
                body = {'from_family': family, 'to_family': target, 'environment': passed['dependencies']['environment'],
                        'operation': 'font_family_only_v1', 'requires_allow_font_fallback': True,
                        'training_task': info['task_id'], 'content_geometry_signature': before['font_independent_signature'],
                        'evidence_locks': {failed_path.relative_to(output).as_posix(): failed_sha,
                                           passed_path.relative_to(output).as_posix(): passed_sha},
                        'certification': 'same_content_geometry_with_actual_office_export',
                        'quality_scope': 'font coverage and mechanical rendering', 'phase': 'probation'}
                identifier = hashlib.sha256(json.dumps(body, sort_keys=True).encode()).hexdigest()
                validations = {}
                for validation_info, validation_path, validation_sha, receipt, page in pages:
                    source_signature = validation_info.get('source_signature')
                    if (receipt.get('mechanical_status') != 'passed' or receipt.get('findings') or
                            validation_info['task_id'] == info['task_id'] or not source_signature or
                            not info.get('source_signature') or
                            source_signature == info.get('source_signature') or
                            receipt.get('dependencies', {}).get('environment') != body['environment'] or
                            not any(item.get('rule_id') == identifier for item in receipt.get('applied_font_rules', []))):
                        continue
                    validations[source_signature] = {'task_id': validation_info['task_id'], 'source_signature': source_signature,
                                                     'receipt': validation_path.relative_to(output).as_posix(), 'sha256': validation_sha}
                records = list(validations.values())
                locks = {**body['evidence_locks'], **{row['receipt']: row['sha256'] for row in records}}
                rules[identifier] = {'id': identifier, **body, 'evidence_locks': locks,
                                     'phase': 'active' if len(records) >= 2 else 'probation',
                                     'independent_validations': records, 'quality_cost_promoted': False}
    path = store / 'delivery-font-rules.json'
    value = {'version': 1, 'rules': list(rules.values())[:16], 'model_requests': 0}
    temporary = path.with_suffix('.tmp')
    temporary.write_text(json.dumps(value, ensure_ascii=False, indent=2), encoding='utf-8')
    temporary.chmod(0o600)
    temporary.replace(path)
    return value
