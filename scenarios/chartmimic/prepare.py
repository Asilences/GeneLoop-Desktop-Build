"""Freeze official image-only ChartMimic inputs separately from evaluator code."""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
import re
import subprocess
import tarfile


def sha(data):
    return hashlib.sha256(data).hexdigest()


def prepare(official, archive, output, roles, subset='direct_600'):
    official, archive, output = map(Path, (official, archive, output))
    if subset.startswith('customized'):
        raise ValueError('customized_requires_original_image_and_official_data_injection_audit')
    if subset not in ('direct_600', 'direct_1800'):
        raise ValueError('unsupported_official_subset')
    ids = [item for group in roles.values() for item in group]
    if len(ids) != len(set(ids)) or not ids or any(not re.fullmatch(r'[A-Za-z0-9]+_[0-9]+', i) for i in ids):
        raise ValueError('disjoint_task_ids_required')
    metadata_file = official / 'dimentions_info.jsonl'
    # Metadata contains reference source code. Only officially supplied dimensions
    # are projected into the solver tree.
    metadata = {row['idx']: row for row in map(json.loads, metadata_file.read_text().splitlines())}
    prompt_file = official / 'chart2code/prompts/DirectAgent/gpt-4-vision-preview.json'
    template = json.loads(prompt_file.read_text())['instruction']
    output.mkdir(parents=True, mode=0o700, exist_ok=False)
    manifest = {'format': 'chartmimic_input_freeze_v1', 'subset': subset, 'roles': roles,
                'official_commit': subprocess.check_output(['git', '-C', str(official), 'rev-parse', 'HEAD'], text=True).strip(),
                'archive_sha256': sha(archive.read_bytes()), 'metadata_sha256': sha(metadata_file.read_bytes()),
                'prompt_sha256': sha(prompt_file.read_bytes()), 'tasks': {}}
    with tarfile.open(archive) as tar:
        for task_id in ids:
            row = metadata[task_id]
            solver = output / 'solver' / task_id
            evaluator = output / 'evaluation-only' / task_id
            solver.mkdir(parents=True)
            evaluator.mkdir(parents=True)
            members = {}
            for suffix, target in (('.png', solver / 'reference.png'), ('.py', evaluator / (task_id + '.py'))):
                member = tar.getmember('./' + subset + '/' + task_id + suffix)
                if not member.isfile():
                    raise ValueError('official_regular_file_required')
                raw = tar.extractfile(member).read()
                target.write_bytes(raw)
                members[suffix] = sha(raw)
            instruction = template.format(width=row['width'], height=row['height'])
            (solver / 'instruction.md').write_text(instruction, encoding='utf-8')
            manifest['tasks'][task_id] = {'width': row['width'], 'height': row['height'],
                'input_image_sha256': members['.png'], 'reference_code_sha256': members['.py'],
                'instruction_sha256': sha(instruction.encode()),
                'role': next(role for role, tasks in roles.items() if task_id in tasks)}
    (output / 'manifest.json').write_text(json.dumps(manifest, indent=2) + '\n')
    return manifest


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--official', required=True, type=Path)
    parser.add_argument('--archive', required=True, type=Path)
    parser.add_argument('--output', required=True, type=Path)
    parser.add_argument('--roles', required=True, type=Path)
    parser.add_argument('--subset', default='direct_600')
    args = parser.parse_args()
    value = prepare(args.official, args.archive, args.output, json.loads(args.roles.read_text()), args.subset)
    print(json.dumps({'status': 'frozen', 'tasks': list(value['tasks']), 'official_commit': value['official_commit']}))
