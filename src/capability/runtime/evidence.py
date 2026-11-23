"""Read and retain capability evidence without depending on learning orchestration."""

import hashlib
import json
import os
from pathlib import Path


def save(path, value):
    with Path(path).open('x', encoding='utf8') as f:
        os.chmod(path, 0o600)
        json.dump(value, f, ensure_ascii=False, allow_nan=False, indent=2)
        f.flush(); os.fsync(f.fileno())


def read(path):
    return json.loads(Path(path).read_text(encoding='utf-8'))


def evidence(ref):
    raw = Path(ref['path']).read_bytes()
    if hashlib.sha256(raw).hexdigest() != ref['sha256']:
        raise ValueError('improvement_evidence_changed')
    return raw
