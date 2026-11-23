"""Recover export-ignored regular files from the same pinned Git tree.

GitHub archives honor export-ignore. Read tree/blob bytes only; no checkout,
code execution, metadata changes, credential use or secret validation.
"""
import argparse
from concurrent.futures import ThreadPoolExecutor
import csv
import hashlib
import json
from pathlib import Path, PurePosixPath
import time
import urllib.error
import urllib.parse
import urllib.request
import zlib


def get(url):
    last = None
    for attempt in range(3):
        try:
            request = urllib.request.Request(url, headers={'User-Agent': 'GeneLoop-offline-privacy-evaluation'})
            with urllib.request.urlopen(request, timeout=90) as response:
                return response.read()
        except Exception as exc:
            last = exc
            time.sleep(attempt + 1)
    raise last


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--root', type=Path, required=True)
    args = parser.parse_args()
    source = args.root.resolve()
    manifest_path = source.parent / 'creddata-preparation.json'
    manifest = json.loads(manifest_path.read_text())
    snapshot = json.loads((source / 'snapshot.json').read_text())
    by_short = {f'{zlib.crc32(bytes.fromhex(key)):08x}': (key, url) for key, url in snapshot.items()}

    def recover(row):
        if row['status'] == 'complete':
            return row
        key, url = by_short[row['repo']]
        upstream = url.removeprefix('https://github.com/').removesuffix('.git')
        target = source / 'tmp' / key
        with (source / 'meta' / f"{row['repo']}.csv").open() as f:
            wanted = {r['FileID'] for r in csv.DictReader(f)}
        try:
            found = set()
            cache = source.parent / 'git-tree-cache'
            cache.mkdir(exist_ok=True)

            def tree(sha, recursive):
                cached = cache / f'{sha}-{int(recursive)}.json'
                if not cached.exists():
                    cached.write_bytes(get(f'https://api.github.com/repos/{upstream}/git/trees/{sha}' + ('?recursive=1' if recursive else '')))
                return json.loads(cached.read_text())

            def visit(sha, prefix=''):
                data = tree(sha, True)
                for entry in data['tree']:
                    if entry['type'] != 'blob' or entry['mode'] not in ('100644', '100755'):
                        continue
                    path = prefix + entry['path']
                    file_id = hashlib.sha256(path.encode()).hexdigest()[:8]
                    parts = PurePosixPath(path).parts
                    root_license = len(parts) == 1 and any(s in parts[0].upper() for s in ('LICEN', 'COPYING'))
                    if file_id not in wanted and not root_license:
                        continue
                    assert parts and '..' not in parts
                    output = target.joinpath(*parts)
                    assert output.resolve().is_relative_to(target.resolve())
                    content = output.read_bytes() if output.is_file() else get(f'https://raw.githubusercontent.com/{upstream}/{key[:40]}/{urllib.parse.quote(path)}')
                    assert hashlib.sha1(b'blob ' + str(len(content)).encode() + b'\0' + content).hexdigest() == entry['sha']
                    output.parent.mkdir(parents=True, exist_ok=True)
                    output.write_bytes(content)
                    if file_id in wanted:
                        found.add(file_id)
                if data.get('truncated') and found != wanted:
                    direct = tree(sha, False)
                    for branch in direct['tree']:
                        if branch['type'] == 'tree':
                            visit(branch['sha'], prefix + branch['path'] + '/')
                            if found == wanted:
                                break

            visit(key[:40])
            updated = {'repo': row['repo'], 'status': 'complete' if found == wanted else 'unavailable',
                       'files': len(found), 'expected': len(wanted), 'missing_count': len(wanted - found),
                       'recovery': 'pinned_git_tree_verified_blob_sha1'}
            if found == wanted:
                (target / '.benchmark-complete.json').write_text(json.dumps(updated))
        except Exception as exc:
            updated = {**row, 'tree_recovery_error': type(exc).__name__, 'http_status': getattr(exc, 'code', None)}
        print(json.dumps(updated), flush=True)
        return updated

    with ThreadPoolExecutor(max_workers=4) as pool:
        rows = list(pool.map(recover, manifest['results']))
    manifest['results'] = rows
    before = source.parent / 'creddata-preparation-before-tree-recovery.json'
    before.write_text(manifest_path.read_text())
    manifest_path.write_text(json.dumps(manifest, indent=2))
    print(json.dumps({'complete': sum(r['status'] == 'complete' for r in rows), 'total': len(rows)}), flush=True)


if __name__ == '__main__':
    main()
