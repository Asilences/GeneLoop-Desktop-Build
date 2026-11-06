"""Adapt frozen bibliography runs to the original investigation and task host."""
from __future__ import annotations

import json
import shutil
from decimal import Decimal
from pathlib import Path

from src.adapters.capability_contract import capability_digest
from src.adapters.capability_decision_evidence import _web, record_web_decision, inspect_decision
from src.adapters.capability_feedback import file_ref, verify
from src.adapters.capability_improvement import save
from src.adapters.capability_trajectory import project_web_task

OWNER = 'script-motif-real'
SCOPE = 'bibliography-integrity-history'
TASK_FILES = ('task-state.json', 'effective-config.json', 'task.json', 'events.jsonl',
              'reuse-boundaries.jsonl', 'learning-accounting.json', 'answer.md', 'answer.json', 'ledger.jsonl')


def prepare_history(manifest_ref, output, prompt_ref, *, discovery_papers, validation_papers, evaluation_papers):
    """Copy unchanged original bytes; host projections retain historical exposure."""
    manifest = json.loads(verify(manifest_ref))
    prompt = verify(prompt_ref).decode('utf-8')
    groups = [set(discovery_papers), set(validation_papers), set(evaluation_papers)]
    if any(groups[i] & groups[j] for i in range(3) for j in range(i)):
        raise ValueError('paper_history_role_overlap')
    output = Path(output)
    output.mkdir(parents=True, exist_ok=False, mode=0o700)
    runs = []
    for record in manifest['records']:
        paper = record['paper']
        if paper not in set.union(*groups):
            continue
        role = ('discovery' if paper in groups[0] else 'development' if paper in groups[1] else 'evaluation')
        task = output / 'runs' / record['task_id'] / 'tasks' / record['task_id']
        task.mkdir(parents=True)
        original = Path(record['task']['path']).parent
        for field in ('task', 'events', 'source'):
            verify(record[field])
        if record['source']['sha256'] != record['source_identity']:
            raise ValueError('paper_history_source_changed')
        copied = []
        for name in TASK_FILES:
            source = original / name
            if source.exists():
                destination = task / name
                shutil.copyfile(source, destination)
                if file_ref(source)['sha256'] != file_ref(destination)['sha256']:
                    raise ValueError('paper_history_copy_changed')
                copied.append(str(destination.relative_to(output)))
        shutil.copyfile(record['source']['path'], task / 'input.bib')
        facts = {'paper': paper, 'repeat': record['repeat'], 'arm': record['arm'],
                 'source_sha256': record['source_identity'], 'quality_checks': record['quality_checks'],
                 'task_spec_hash': prompt_ref['sha256'], 'exposure': 'previously_observed_historical_replay',
                 'method_version': file_ref(task / 'effective-config.json')['sha256'], 'role': role}
        save(task / 'facts.json', facts)
        runs.append({'task_directory': str(task.relative_to(output)), 'role': role, 'paper': paper,
                     'original_files': copied, 'task_id': record['task_id']})
    save(output / 'prompt.json', {'text': prompt, 'original': prompt_ref})
    save(output / 'manifest.json', {'owner': OWNER, 'scope': SCOPE, 'runs': runs,
                                   'exposure': 'historical_replay', 'model_requests': 0})
    return file_ref(output / 'manifest.json')


def index_history(manifest_ref, output):
    """Bind portable originals to existing decision evidence on the executing host."""
    manifest = json.loads(verify(manifest_ref))
    root = Path(manifest_ref['path']).parent
    output = Path(output)
    output.mkdir(parents=True, exist_ok=False, mode=0o700)
    prompt = json.loads((root / 'prompt.json').read_text())['text']
    entries, excluded = [], {'development': [], 'evaluation': []}
    for run in manifest['runs']:
        task = (root / run['task_directory']).resolve()
        if run['role'] != 'discovery':
            excluded[run['role']].extend(file_ref(path) for path in task.iterdir() if path.is_file())
            continue
        original = _web(task, OWNER)
        context_path = output / (run['task_id'] + '-context.json')
        save(context_path, {'format': 'capability_decision_context_v1', 'owner': OWNER,
             'source_evidence': original['evidence'], 'objective': prompt,
             'state': 'Historical bibliography inspection; method and results are available through evidence.',
             'remaining_judgments': [], 'interactions': [],
             'outcome': 'Original answer and historical oracle findings are retained; improvement is unmeasured.'})
        reference = record_web_decision(task, OWNER, relation='bibliography-integrity',
            approved_context=file_ref(context_path), output=output / (run['task_id'] + '-decision.json'))
        entries.append({'split': 'training', 'scope': SCOPE, 'evidence': reference})
    return entries, excluded


def inspect_history(reference, owner):
    record = json.loads(verify(reference))
    task = Path(record['source']['directory'])
    row = inspect_decision(reference, owner)
    facts_ref = file_ref(task / 'facts.json')
    facts = json.loads(verify(facts_ref))
    if facts['role'] != 'discovery':
        raise ValueError('paper_history_evaluation_excluded')
    source_ref = file_ref(task / 'input.bib')
    if source_ref['sha256'] != facts['source_sha256']:
        raise ValueError('paper_history_source_changed')
    row['source_identity'] = facts['source_sha256']
    row['decision_context']['state'] = facts
    row['quality'] = 'passed' if all(facts['quality_checks'].values()) else 'failed'
    row['quality_review'] = {'scope': 'original_historical_oracle_checks', 'exposure': facts['exposure']}
    row['quality_findings'] = [{'id': key, 'status': 'passed' if passed else 'failed',
        'observation': 'Original frozen bibliography verifier result; inspect source and answer to investigate.',
        'evidence': [facts_ref, source_ref]} for key, passed in facts['quality_checks'].items()]
    trace = project_web_task(task, owner)
    row['action_overview'] = [{'sequence': index, 'call_id': step['call_id'], 'tool': step['tool'],
        'status': step['status'], 'call_event_index': step['call_event_index'],
        'result_event_index': step['result_event_index'],
        'boundary': step['boundary'], 'evidence_strength': 'observed',
        'dependencies': step['dependencies']} for index, step in enumerate(trace['steps'])]
    row['steps'] = trace['steps']
    row['action_scope'] = 'Observed original calls; adjacency is not a data dependency or causal explanation.'
    accounting = json.loads(verify(trace['accounting']))
    receipts = accounting['request_receipts']
    amounts = [receipt.get('observed_peak_usd') for receipt in receipts]
    row['observed_cost_usd'] = (str(sum((Decimal(str(value)) for value in amounts), Decimal(0)))
                                if amounts and all(value is not None for value in amounts) else None)
    row['model_decision_count'] = len(receipts)
    row['cost_attribution'] = 'Original task request receipts only; research and new evaluation recorded separately.'
    row['evidence'].extend([facts_ref, source_ref])
    for name in ('answer.md', 'answer.json'):
        if (task / name).is_file():
            row['evidence'].append(file_ref(task / name))
    return row


def prepare_evaluation_tasks(manifest_ref, oracle_ref):
    """Use original gold values in the existing isolated task adapter."""
    manifest = json.loads(verify(manifest_ref))
    root = Path(manifest_ref['path']).parent
    oracle = json.loads(verify(oracle_ref))
    prompt = json.loads((root / 'prompt.json').read_text())['text']
    seen = set()
    for run in manifest['runs']:
        if run['role'] == 'discovery' or run['paper'] in seen:
            continue
        seen.add(run['paper'])
        task_id = 'paper-' + run['paper'].replace('.', '-').lower()
        target = root / 'evaluation-tasks' / run['role'] / task_id
        (target / 'environment').mkdir(parents=True)
        (target / 'tests').mkdir()
        source = root / run['task_directory'] / 'input.bib'
        shutil.copyfile(source, target / 'environment/input.bib')
        (target / 'instruction.md').write_text(prompt + '\n\nTechnical delivery for this isolated replay: '
            'the attachment is /root/input.bib. Save the requested JSON to /root/answer.json. '
            'Do not modify the input. Explanations may be given in the final message.\n')
        (target / 'task.toml').write_text('''version = "1.0"
[metadata]
category = "historical-bibliography-replay"
[agent]
timeout_sec = 300.0
[verifier]
timeout_sec = 120.0
[environment]
build_timeout_sec = 600.0
cpus = 1
memory_mb = 2048
storage_mb = 4096
gpus = 0
allow_internet = false
''')
        (target / 'environment/Dockerfile').write_text('FROM python:3.12-slim\n'
            'RUN pip install --no-cache-dir pytest==8.4.1 pytest-json-ctrf==0.3.5\n'
            'WORKDIR /root\nCOPY input.bib /root/input.bib\n')
        save(target / 'tests/gold.json', oracle[run['paper']]['gold'])
        (target / 'tests/test_outputs.py').write_text('''import json
from pathlib import Path
import pytest

def normalized(value):
    if isinstance(value, dict):
        return {key: normalized(child) for key, child in value.items()}
    if isinstance(value, list):
        return sorted((normalized(child) for child in value), key=lambda x: json.dumps(x, sort_keys=True))
    return value

@pytest.mark.parametrize("field", ["entry_count", "unique_key_count", "duplicate_keys", "missing_fields", "same_title_groups"])
def test_original_gold(field):
    expected = json.loads(Path("/tests/gold.json").read_text())
    answer = json.loads(Path("/root/answer.json").read_text())
    assert field in answer
    if field in ("entry_count", "unique_key_count"):
        assert type(answer[field]) is int
    assert normalized(answer[field]) == normalized(expected[field])
''')
        (target / 'tests/test.sh').write_text('''#!/bin/bash
mkdir -p /logs/verifier
python -m pytest --ctrf /logs/verifier/ctrf.json /tests/test_outputs.py -rA
status=$?
if [ "$status" -eq 0 ]; then echo 1 > /logs/verifier/reward.txt; else echo 0 > /logs/verifier/reward.txt; fi
exit "$status"
''')
