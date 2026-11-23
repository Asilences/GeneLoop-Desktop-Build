"""Fetch pinned regular files only, then use CredData's original preparation.

Run inside a private copy of Samsung/CredData. Never executes fetched projects.
Unlike upstream's permissive downloader, missing labels abort preparation.
"""
import argparse
from concurrent.futures import ThreadPoolExecutor, as_completed
import csv
import hashlib
import json
from pathlib import Path, PurePosixPath
import re
import tarfile
import time
import urllib.request
import zlib


def fetch(root, repo_id, url):
    assert re.fullmatch(r"[a-f0-9]{64}", repo_id)
    repo8 = f"{zlib.crc32(bytes.fromhex(repo_id)):08x}"
    with (root / 'meta' / f'{repo8}.csv').open() as f:
        wanted = {row['FileID'] for row in csv.DictReader(f)}
    target = root / 'tmp' / repo_id
    target.mkdir(parents=True, exist_ok=True)
    marker = target / '.benchmark-complete.json'
    if marker.exists():
        return json.loads(marker.read_text())
    upstream = url.removeprefix('https://github.com/').removesuffix('.git')
    assert re.fullmatch(r'[\w.-]+/[\w.-]+', upstream)
    archive_url = f'https://codeload.github.com/{upstream}/tar.gz/{repo_id[:40]}'
    found = set()
    last_error = None
    for attempt in range(3):
        try:
            with urllib.request.urlopen(archive_url, timeout=180) as response:
                with tarfile.open(fileobj=response, mode='r|gz') as archive:
                    for member in archive:
                        if not member.isfile():
                            continue
                        parts = PurePosixPath(member.name).parts[1:]
                        if not parts or any(p in ('..', '.') for p in parts):
                            continue
                        relative = '/'.join(parts)
                        file_id = hashlib.sha256(relative.encode()).hexdigest()[:8]
                        license_file = len(parts) == 1 and any(s in parts[0].upper() for s in ('LICEN', 'COPYING'))
                        if file_id not in wanted and not license_file:
                            continue
                        output = target.joinpath(*parts)
                        assert output.resolve().is_relative_to(target.resolve())
                        output.parent.mkdir(parents=True, exist_ok=True)
                        content = archive.extractfile(member).read()
                        output.write_bytes(content)
                        if file_id in wanted:
                            found.add(file_id)
            missing = wanted - found
            if missing:
                raise ValueError(f'missing {len(missing)} labeled files')
            result = {'repo': repo8, 'files': len(found), 'status': 'complete'}
            marker.write_text(json.dumps(result))
            return result
        except Exception as exc:
            last_error = type(exc).__name__
            time.sleep(attempt + 1)
    return {'repo': repo8, 'status': 'unavailable', 'error_type': last_error,
            'found': len(found), 'expected': len(wanted)}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--root', type=Path, required=True)
    parser.add_argument('--workers', type=int, default=8)
    args = parser.parse_args()
    root = args.root.resolve()
    snapshot = json.loads((root / 'snapshot.json').read_text())
    meta_hashes = {p.name: hashlib.sha256(p.read_bytes()).hexdigest() for p in (root / 'meta').glob('*.csv')}
    results = []
    with ThreadPoolExecutor(max_workers=args.workers) as pool:
        futures = [pool.submit(fetch, root, key, value) for key, value in snapshot.items()]
        for future in as_completed(futures):
            results.append(future.result())
            if len(results) % 20 == 0:
                print(json.dumps({'prepared': len(results), 'unavailable': sum(r['status'] != 'complete' for r in results)}), flush=True)
    manifest = {'repositories': len(snapshot), 'results': sorted(results, key=lambda x: x['repo']), 'meta_sha256': meta_hashes}
    (root.parent / 'creddata-preparation.json').write_text(json.dumps(manifest, indent=2))
    assert all(row['status'] == 'complete' for row in results), 'Unavailable repositories: gold metadata must remain unchanged'
    import os
    import sys
    os.chdir(root)
    sys.path.insert(0, str(root))
    from download_data import move_files
    from obfuscate_creds import obfuscate_creds
    assert not move_files(snapshot, 'data'), 'Upstream preparation attempted to exclude metadata'
    assert meta_hashes == {p.name: hashlib.sha256(p.read_bytes()).hexdigest() for p in (root / 'meta').glob('*.csv')}
    obfuscate_creds('meta', 'data', 0)
    data_hashes = {str(p.relative_to(root)): hashlib.sha256(p.read_bytes()).hexdigest() for p in (root / 'data').rglob('*') if p.is_file()}
    manifest['prepared_files'] = len(data_hashes)
    manifest['data_digest'] = hashlib.sha256(json.dumps(data_hashes, sort_keys=True).encode()).hexdigest()
    (root.parent / 'creddata-preparation.json').write_text(json.dumps(manifest, indent=2))
    print(json.dumps({'repositories': len(snapshot), 'prepared_files': len(data_hashes), 'status': 'complete'}), flush=True)


if __name__ == '__main__':
    main()
