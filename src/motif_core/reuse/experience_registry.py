"""Immutable unified experience versions. Admission never promotes a mere candidate."""
from __future__ import annotations
import hashlib
import json
import os
from pathlib import Path


def digest(value):
    return hashlib.sha256(json.dumps(value, sort_keys=True, ensure_ascii=False,
                                    separators=(',', ':')).encode()).hexdigest()


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def read(path):
    return json.loads(Path(path).read_text(encoding='utf-8'))


def durable(path, value, exclusive=False):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
    temporary = path if exclusive else path.with_suffix(path.suffix + '.tmp')
    with temporary.open('x' if exclusive else 'w', encoding='utf-8') as stream:
        stream.write(json.dumps(value, ensure_ascii=False, indent=2) + '\n')
        stream.flush()
        os.fsync(stream.fileno())
    temporary.chmod(0o600)
    if not exclusive:
        temporary.replace(path)


class ExperienceRegistry:
    """One offline writer; immutable objects/snapshots with an atomic current pointer."""
    def __init__(self, root):
        self.root = Path(root).resolve()
        self.root.mkdir(parents=True, exist_ok=True, mode=0o700)

    def object(self, source):
        source = Path(source)
        value = source.read_bytes()
        h = hashlib.sha256(value).hexdigest()
        relative = 'objects/' + h + '.json'
        p = self.root / relative
        if p.exists():
            if p.read_bytes() != value:
                raise ValueError('immutable experience object changed')
        else:
            p.parent.mkdir(exist_ok=True, mode=0o700)
            with p.open('xb') as stream:
                stream.write(value)
                stream.flush()
                os.fsync(stream.fileno())
            p.chmod(0o600)
        return relative, h

    def entry(self, kind, payload, runtime_source, certificate=None, *, verify_certificate=None):
        if kind in ('operation_graph','management_program','file_script') and certificate is None:raise ValueError('operation/program requires independent actual certification')
        if certificate is not None and verify_certificate is None:
            raise ValueError('experience certificate verifier required')
        value = read(payload)
        field = 'script_digest' if kind.startswith('script_') else 'library_digest' if kind == 'read_library' else 'policy_digest'
        h = value.get(field)
        if h != digest({k: v for k, v in value.items() if k != field}):
            raise ValueError('invalid original experience signature')
        if kind.startswith('script_'):
            if certificate is None:
                raise ValueError('script requires independent certification')
            verify_certificate(value, certificate, sha(payload))
            if kind == 'script_v2' and value['runtime_source'] != {n: runtime_source[n] for n in value['runtime_source']}:
                raise ValueError('script runtime closure differs from certification')
        else:
            if kind == 'read_library' and value.get('status') != 'certified_read_library':
                raise ValueError('unvalidated read library')
            artifacts = value.get('artifacts', []) if kind == 'read_library' else [value.get('artifact', {})]
            if not artifacts:
                raise ValueError('empty Motif library')
            for a in artifacts:
                training = a.get('source_task_fingerprints', [])
                if (a.get('status') not in ('trace_validated_read_only', 'trace_validated_effectful')
                        or a.get('certified_digest') != digest({k: v for k, v in a.items() if k != 'certified_digest'})
                        or len(training) < (1 if kind=='file_script' else 2) or len(set(training)) != len(training)
                        or not a.get('validation_task_fingerprint') or a['validation_task_fingerprint'] in training):
                    raise ValueError('uncertified or overlapping Motif evidence')
            if certificate is not None:
                verify_certificate(value, certificate, sha(payload))
        relative, raw = self.object(payload)
        entry = {'entry_id': h, 'kind': kind, 'payload': relative, 'sha256': raw,
                 'artifact_digest': h, 'runtime_source': runtime_source, 'state': 'active'}
        if certificate:
            file, cert_sha = self.object(certificate)
            entry['certificate'] = {'file': file, 'sha256': cert_sha}
        return entry

    def load(self, file=None):
        if file is None:
            pointer = read(self.root / 'current.json')
            file = self.root / pointer['file']
            if sha(file) != pointer['sha256']:
                raise ValueError('registry pointer changed')
        state = read(file)
        if state['registry_digest'] != digest({k: v for k, v in state.items() if k != 'registry_digest'}):
            raise ValueError('registry signature changed')
        for entry in state['entries']:
            if sha(self.root / entry['payload']) != entry['sha256']:
                raise ValueError('experience payload changed')
        return state

    def publish(self, additions=(), disable=(), reason='independent certification', expected=None):
        previous = self.load() if (self.root / 'current.json').exists() else None
        generation = previous['generation'] if previous else 0
        if expected is not None and expected != generation:
            raise ValueError('registry writer/version conflict')
        entries = {r['entry_id']: dict(r) for r in previous['entries']} if previous else {}
        for key in disable:
            if key in entries:
                entries[key].update(state='disabled', disabled_reason=reason)
        for row in additions:
            if row['entry_id'] in entries:
                raise ValueError('cannot silently replace or reenable an old experience')
            entries[row['entry_id']] = {**row, 'activated_generation': generation + 1}
        state = {'schema_version': 1, 'format': 'sss-experience-registry-v1', 'generation': generation + 1,
                 'parent_digest': previous['registry_digest'] if previous else None, 'reason': reason,
                 'entries': list(entries.values()), 'automatic_selection_uses_profile_id': False}
        state['registry_digest'] = digest(state)
        file = self.root / 'versions' / (f'{generation + 1:06d}.json')
        durable(file, state, exclusive=True)
        durable(self.root / 'current.json', {'file': str(file.relative_to(self.root)), 'sha256': sha(file),
                                            'registry_digest': state['registry_digest']})
        return file
