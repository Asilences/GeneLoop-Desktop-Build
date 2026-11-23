"""Read-only presentation of the account's certified desktop motifs."""
import json
import re
import sys
import time
from collections import Counter
from functools import lru_cache
from hashlib import sha256

from src.adapters.desktop.desktop_rsi import CONTRACTS, VERSION, artifact_signature, read, root_path
from src.adapters.geneloop_learning_trace import private_json

MOTIF_ID = re.compile(r'motif-[0-9a-f]{24}')
ATTEMPT_ID = re.compile(r'[0-9a-f]{32}')
INVOCATION_ID = re.compile(r'[0-9a-f]{8}(?:-[0-9a-f]{4}){3}-[0-9a-f]{12}')
SCENES = {'chat', 'files', 'data', 'paper', 'ppt', 'video'}
EXPIRY_MS = 30 * 86400000


def catalog(root):
    now = time.time() * 1000
    owner = read(root / 'owner.json')['principal']

    @lru_cache(maxsize=256)
    def source_valid(identity):
        try:
            if not ATTEMPT_ID.fullmatch(identity):
                return False
            task = root / 'tasks' / identity
            meta = read(task / 'task.json')
            admission = read(task / 'admission.json')
            return (meta['principal'] == owner and meta['attempt_id'] == identity
                    and meta['status'] == 'completed'
                    and meta['finished_at'] + EXPIRY_MS > now
                    and admission['code_version'] == VERSION
                    and sha256(private_json(task / 'events.jsonl')).hexdigest() == admission['events_sha256'])
        except (OSError, ValueError, KeyError, TypeError):
            return False

    completed = Counter()
    seen = set()
    try:
        feedback = private_json(root / 'feedback.jsonl')
    except FileNotFoundError:
        feedback = b''
    except (ValueError, OSError):
        feedback = None
    for line in (feedback or b'').splitlines():
        try:
            result = json.loads(line)
            motif, invocation = result['motif_id'], result['invocation_id']
            if (result['status'] == 'completed' and MOTIF_ID.fullmatch(motif)
                    and INVOCATION_ID.fullmatch(invocation) and invocation not in seen):
                completed[motif] += 1
                seen.add(invocation)
        except (ValueError, KeyError, TypeError):
            continue

    rows = []
    for path in sorted((root / 'motifs').glob('motif-*.json'), reverse=True):
        name = path.stem
        if not MOTIF_ID.fullmatch(name) or (path.parent / (name + '.suspended')).exists():
            continue
        try:
            if path.stat().st_size > 256 * 1024:
                continue
            item = read(path)
            artifact = item['artifact']
            certificate = artifact['certified_digest']
            tools = artifact['tools']
            if (item['format'] != 'geneloop.desktop-read-motif/v1' or item['id'] != name
                    or item['scene'] not in SCENES or item['code_version'] != VERSION
                    or item['certification_scope'] != 'independent_trace_structure'
                    or artifact['status'] != 'trace_validated_read_only'
                    or name != 'motif-' + certificate[:24] or artifact_signature(artifact) != certificate
                    or not 2 <= len(tools) <= 4 or not all(tool in CONTRACTS for tool in tools)):
                continue
            witnesses = [*artifact['source_trace_ids'], artifact['validation_trace_id']]
            if not 3 <= len(witnesses) <= 100 or len(set(witnesses)) != len(witnesses):
                continue
            if not all(source_valid(identity) for identity in witnesses):
                continue
            rows.append({'id': name, 'scene': item['scene'], 'tools': tools,
                         'certificate': certificate, 'witnesses': len(witnesses),
                         'reuses': completed[name] if feedback is not None else None})
            if len(rows) >= 256:
                break
        except (OSError, ValueError, KeyError, TypeError):
            continue
    return rows


if __name__ == '__main__':
    print(json.dumps(catalog(root_path(sys.argv[1])), ensure_ascii=True))
