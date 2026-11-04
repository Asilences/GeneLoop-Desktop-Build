"""Offline CLI protocol diagnostics over synthetic native events."""
import importlib.util
import json
from pathlib import Path

from src.adapters.capability_feedback import file_ref
from src.adapters.capability_decision_evidence import record_web_decision
from src.adapters.capability_trajectory import project_web_task
from tests.test_capability_decision_evidence import web_task, context, put
from tests.test_capability_feedback import fixture


def test_preview_uses_decision_evidence_and_preserves_private_messages(tmp_path):
    root = Path(__file__).resolve().parents[1]
    spec = importlib.util.spec_from_file_location('strategy_cli_diagnostic', root / 'scripts/run-strategy-evolution.py')
    cli = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(cli)
    cli.ROOT = tmp_path
    code = tmp_path / 'src/adapters/capability_evolution_agent.py'
    code.parent.mkdir(parents=True)
    code.write_bytes((root / 'src/adapters/capability_evolution_agent.py').read_bytes())
    _, library, _, _ = fixture(tmp_path)
    snapshot = put(tmp_path / 'snapshot.json', library['snapshot'])
    entries = []
    for index in range(2):
        task = web_task(tmp_path, identity='web-' + str(index), source='independent-' + str(index))
        approved = context(tmp_path / f'context-{index}.json', project_web_task(task, 'owner')['evidence'])
        ref = record_web_decision(task, 'owner', relation='shared-decision', approved_context=approved,
                                  output=tmp_path / f'decision-{index}.json')
        entries.append({'split': 'training', 'scope': 'paper', 'evidence': ref})
    host = tmp_path / 'host.py'
    host.write_text('raise RuntimeError("preview must not execute host code")', encoding='utf-8')
    manifest = put(tmp_path / 'manifest.json', {'snapshot': snapshot, 'observations': entries,
        'scope': 'paper', 'target': 'task', 'feedback_directory': str(tmp_path / 'feedback'),
        'ledger_root': str(tmp_path / 'ledger'), 'host_adapter': file_ref(host)})
    output = tmp_path / '.local/preview'
    report = cli.execute(manifest, output, budget_usd='0')
    assert report['status'] == 'preview' and report['model_requests'] == 0
    visible = json.loads((output / 'external-context.json').read_text())
    assert visible['independent_sources'] == 2
    assert 'decision_context' in visible['observations'][0]
    assert 'PRIVATE' not in json.dumps(visible)
    assert not (tmp_path / 'ledger').exists()
