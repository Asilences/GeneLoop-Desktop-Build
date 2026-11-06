"""Free booking/export diagnostics; no upstream calls or real RSI claims."""
from copy import deepcopy
import json
from types import SimpleNamespace

import pytest

from src.adapters import capability_proposal as pilot
from src.adapters.efficiency_rsi_measurement import digest, measure_study
from src.adapters.efficiency_rsi_registry import StudyRequestRegistry
from tests.test_efficiency_rsi_measurement import example


def registered(tmp_path):
    plan, obs, _ = example(tmp_path)
    registry = StudyRequestRegistry(plan, tmp_path/'bookings.jsonl', create=True)
    paths = []
    for cell in plan['cells']:
        path = tmp_path/cell['id']/'attempt-0'
        path.mkdir(parents=True)
        registry.register_owner(path, cell['id']+'-1', cell_id=cell['id'])
        paths.append(path)
    return plan, obs, registry, paths


def test_booking_export_round_trip_and_reopen_preserve_ownership(tmp_path):
    plan, obs, registry, paths = registered(tmp_path)
    refs = [{'ledger_ref': 'ledger-one', 'id': str(i)} for i in (1, 2)]
    for cell, path, ref in zip(plan['cells'], paths, refs):
        registry.bind_request(path, ref['ledger_ref'], ref['id'])
        registry.close_cell(cell['id'])
    exported = StudyRequestRegistry(plan, registry.path).export(refs)
    obs['registry_sha256'] = digest(exported)
    report = measure_study(plan, obs, registry=exported, evidence_root=tmp_path)
    assert report['comparisons'][0]['conditional_cost_saving_usd_decimal'] == '0.2'
    # Equal directory basenames do not merge distinct study-wide attempt IDs.
    assert [b['owner_id'] for b in exported['request_bindings']] == ['baseline-1', 'candidate-1']
    assert exported['cells'][1]['closed']
    obs['attempts'][1]['request_refs'] = []
    obs['overheads'] = [{'id': 'learning', 'category': 'seed_learning', 'request_refs': refs[1:]}]
    with pytest.raises(ValueError):
        measure_study(plan, obs, registry=exported, evidence_root=tmp_path)


def test_duplicate_request_cannot_change_owner_or_be_silently_rebooked(tmp_path):
    _, _, registry, paths = registered(tmp_path)
    registry.bind_request(paths[0], 'ledger', 8)
    before = registry.path.read_bytes()
    for path in paths:
        with pytest.raises(ValueError, match='already_bound'):
            registry.bind_request(path, 'ledger', 8)
        assert registry.path.read_bytes() == before
    registry.bind_request(paths[1], 'different-ledger', 8)
    assert len(registry.export([{'ledger_ref': l, 'id': '8'} for l in ('ledger', 'different-ledger')])['request_refs']) == 2


@pytest.mark.parametrize('refs', [[], [{'ledger_ref': 'ledger', 'id': 'other'}],
    [{'ledger_ref': 'ledger', 'id': '8'}]*2])
def test_incomplete_extra_or_duplicate_provider_inventory_fails(tmp_path, refs):
    _, _, registry, paths = registered(tmp_path)
    registry.bind_request(paths[0], 'ledger', 8)
    with pytest.raises(ValueError, match='inventory_mismatch'):
        registry.export(refs)


def test_overhead_category_fixed_at_registration_and_empty_attempts_retained(tmp_path):
    _, _, registry, paths = registered(tmp_path)
    path = tmp_path/'learning'; path.mkdir()
    registry.register_owner(path, 'learning', category='seed_learning')
    registry.bind_request(path, 'ledger', 9)
    result = registry.export([{'ledger_ref': 'ledger', 'id': '9'}])
    assert result['overhead_ids'] == ['learning']
    assert result['request_bindings'][0] == {'ledger_ref': 'ledger', 'id': '9',
        'owner_type': 'overhead', 'owner_id': 'learning', 'cell_id': None, 'category': 'seed_learning'}
    assert len(result['cells']) == 2 and result['cells'][0]['attempt_ids'] == ['baseline-1']
    with pytest.raises(ValueError, match='owner_already_registered'):
        registry.register_owner(paths[0], 'shifted', category='seed_learning')
    with pytest.raises(ValueError, match='owner_already_registered'):
        registry.register_owner(path, 'baseline-1', category='seed_learning')


def test_closed_cell_rejects_new_attempts_and_requests(tmp_path):
    _, _, registry, paths = registered(tmp_path)
    registry.close_cell('baseline')
    with pytest.raises(ValueError, match='unavailable_owner'):
        registry.bind_request(paths[0], 'ledger', 1)
    path = tmp_path/'next'; path.mkdir()
    with pytest.raises(ValueError, match='invalid_attempt_owner'):
        registry.register_owner(path, 'baseline-2', cell_id='baseline')


def test_owner_can_be_registered_before_existing_proposal_creates_directory(tmp_path):
    _, _, registry, _ = registered(tmp_path)
    future = tmp_path/'future-attempt'
    registry.register_owner(future, 'baseline-2', cell_id='baseline')
    assert not future.exists()
    future.mkdir()
    registry.bind_request(future, 'ledger', 8)
    result = registry.export([{'ledger_ref': 'ledger', 'id': '8'}])
    assert result['request_bindings'][0]['owner_id'] == 'baseline-2'


def test_missing_corrupt_or_changed_plan_evidence_is_not_reconstructed(tmp_path):
    plan, _, registry, _ = registered(tmp_path)
    with pytest.raises(FileExistsError):
        StudyRequestRegistry(plan, registry.path, create=True)
    with pytest.raises(FileNotFoundError):
        StudyRequestRegistry(plan, tmp_path/'missing')
    changed = deepcopy(plan); changed['conditions_sha256'] = 'e'*64
    with pytest.raises(ValueError, match='frozen_plan_changed'):
        StudyRequestRegistry(changed, registry.path)
    with registry.path.open('ab') as stream:
        stream.write(b'{"event":')
    with pytest.raises(ValueError, match='incomplete_journal'):
        StudyRequestRegistry(plan, registry.path)


def test_gate_books_original_counter_and_persists_pending_owner_before_forwarding(tmp_path, monkeypatch):
    plan, _, registry, paths = registered(tmp_path)
    monkeypatch.setenv('KOURI_API_KEY', 'diagnostic-not-a-real-key')
    pilot.write(tmp_path/'budget-checkpoint.json', {'request_count': 7, 'reserved_usd': 2.0})
    ledger = tmp_path/'cost-ledger.jsonl'
    original = b'{"request_id":7,"observed_peak_usd":2.0}\n'
    ledger.write_bytes(original)
    monkeypatch.setattr(pilot, 'create_server', lambda *args: SimpleNamespace(
        serve_forever=lambda: None, shutdown=lambda: None, server_close=lambda: None, server_port=0))
    payload = {'model': 'deepseek-flash', 'max_tokens': 393216,
               'thinking': {'type': 'disabled'}, 'messages': []}
    with pilot.CumulativeProposalGate(tmp_path, study_registry=registry) as gate:
        unknown = tmp_path/'unregistered'; unknown.mkdir(); gate.current = unknown
        with pytest.raises(ValueError, match='unavailable_owner'):
            gate.state.book(json.dumps(payload).encode())
        assert gate.state.request_count == 7
        gate.current = paths[0]
        booked = gate.state.book(json.dumps(payload).encode())  # No HTTP server/upstream.
        assert booked[0] == 8
        refs = [{'ledger_ref': str(ledger), 'id': '8'}]
        exported = StudyRequestRegistry(plan, registry.path).export(refs)
        assert exported['request_bindings'][0]['owner_id'] == 'baseline-1'
        assert gate.costs(paths[0])['observed_model_usd'] is None
        gate.state.log({'request_id': 8, 'observed_peak_usd': .01})
        assert registry.export(refs) == exported  # Settlement cannot reassign owner.
    assert ledger.read_bytes().startswith(original)
    assert pilot.read_json(tmp_path/'budget-checkpoint.json')['request_count'] == 8


def test_journal_write_failure_aborts_booking_without_resetting_reservation(tmp_path, monkeypatch):
    _, _, registry, paths = registered(tmp_path)
    monkeypatch.setenv('KOURI_API_KEY', 'diagnostic-not-a-real-key')
    pilot.write(tmp_path/'budget-checkpoint.json', {'request_count': 7, 'reserved_usd': 2.0})
    (tmp_path/'cost-ledger.jsonl').write_bytes(b'')
    monkeypatch.setattr(pilot, 'create_server', lambda *args: SimpleNamespace(
        serve_forever=lambda: None, shutdown=lambda: None, server_close=lambda: None, server_port=0))
    with pilot.CumulativeProposalGate(tmp_path, study_registry=registry) as gate:
        gate.current = paths[0]
        def failed(*args): raise OSError('diagnostic disk failure')
        monkeypatch.setattr(registry, 'bind_request', failed)
        with pytest.raises(OSError, match='disk failure'):
            gate.state.book(json.dumps({'model': 'deepseek-flash', 'max_tokens': 393216,
                'thinking': {'type': 'disabled'}, 'messages': []}).encode())
        assert gate.state.request_count == 8 and gate.state.reserved_usd > 2
        assert gate.costs(paths[0])['observed_model_usd'] is None
