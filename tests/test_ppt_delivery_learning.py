import hashlib
import json

from src.adapters.ppt_delivery_learning import learn_delivery_fonts
from src.adapters.ppt_design_preflight import apply_font_rule, font_independent_signature


def test_learn_font_rule_from_a_delivered_correction_and_keep_geometry(tmp_path):
    store = tmp_path / 'learning'
    store.mkdir()
    task = tmp_path / 'tasks/task-a'
    receipts = task / 'ppt-delivery-receipts'
    receipts.mkdir(parents=True)
    before = {'page': 1, 'font_independent_signature': 'same-content-geometry', 'preflight': {
        'fonts': {'DejaVu Sans:regular': {}}, 'findings': [{'rule': 'missing_glyphs', 'font_family': 'DejaVu Sans'}]}}
    after = {'page': 1, 'font_independent_signature': 'same-content-geometry', 'preflight': {
        'fonts': {'Noto Sans CJK SC:regular': {}}, 'findings': []}}
    failed = {'dependencies': {'environment': 'fixed-env'}, 'mechanical_status': 'failed', 'page_receipts': [before]}
    passed = {'dependencies': {'environment': 'fixed-env'}, 'mechanical_status': 'passed', 'page_receipts': [after],
              'findings': [], 'artifacts': [{'path': '/work/outputs/deck.pptx', 'sha256': 'delivered'}]}
    (receipts / ('a' * 64 + '.json')).write_text(json.dumps(failed))
    (receipts / ('b' * 64 + '.json')).write_text(json.dumps(passed))
    infos = {'task-a': {'task_id': 'task-a', 'task_dir': str(task), 'state': {'status': 'completed'}, 'source_signature': 'training-paper'}}
    assert learn_delivery_fonts(tmp_path, store, infos, {})['rules'] == []
    result = learn_delivery_fonts(tmp_path, store, infos, {'task-a': {'delivered'}})
    assert len(result['rules']) == 1
    rule = result['rules'][0]
    assert rule['from_family'] == 'DejaVu Sans' and rule['to_family'] == 'Noto Sans CJK SC'
    assert result['model_requests'] == 0
    for name, sha in rule['evidence_locks'].items():
        assert hashlib.sha256((tmp_path / name).read_bytes()).hexdigest() == sha
    original = b'<svg xmlns="http://www.w3.org/2000/svg" font-family="DejaVu Sans"><text x="40" y="50">Accuracy 93.2</text></svg>'
    repaired = apply_font_rule(original, rule)
    assert font_independent_signature(original) == font_independent_signature(repaired)
    assert b'Accuracy 93.2' in repaired
    assert repaired.startswith(b'<svg ') and b'<ns0:' not in repaired
    assert apply_font_rule(original, {**rule, 'from_family': 'Other'}) is None
    deliveries = {'task-a': {'delivered'}}
    for identity in ('task-b', 'task-c'):
        directory = tmp_path / 'tasks' / identity / 'ppt-delivery-receipts'
        directory.mkdir(parents=True)
        future = {**passed, 'applied_font_rules': [{'rule_id': rule['id']}]}
        (directory / ('c' * 64 + '.json')).write_text(json.dumps(future))
        infos[identity] = {'task_id': identity, 'task_dir': str(directory.parent), 'state': {'status': 'completed'}, 'source_signature': identity + '-paper'}
        deliveries[identity] = {'delivered'}
    promoted = learn_delivery_fonts(tmp_path, store, infos, deliveries)['rules'][0]
    assert promoted['phase'] == 'active' and len(promoted['independent_validations']) == 2
    assert promoted['quality_cost_promoted'] is False
    passed['page_receipts'][0]['font_independent_signature'] = 'different-content'
    (receipts / ('b' * 64 + '.json')).write_text(json.dumps(passed))
    assert learn_delivery_fonts(tmp_path, store, infos, {'task-a': {'delivered'}})['rules'] == []
