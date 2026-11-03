"""Shared registration changes cannot silently alter certified scene programs."""
import importlib.util
from pathlib import Path

import pytest
from reexport_compat_fixture import prepare_checkout, remove_expected_difference

ROOT = Path(__file__).resolve().parents[1]
SPEC = importlib.util.spec_from_file_location(
    'shared_invite_export', ROOT / 'scripts/reexport-shared-invite-compat.py')
wrapper = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(wrapper)
compat = wrapper.compat


@pytest.fixture
def frozen_checkout(tmp_path, monkeypatch):
    root = tmp_path / 'checkout'
    published = prepare_checkout(compat, ROOT, root)
    monkeypatch.setattr(compat, 'ROOT', root)
    yield root
    assert all(path.read_bytes() == raw for path, raw in published.items())


def test_gateway_only_export_preserves_program_and_admission(frozen_checkout):
    candidates, registry = compat.review()
    assert [(row['previous'], row['release']) for row in candidates] == [
        ('paper-web-v44', 'paper-web-v45'), ('ppt-master-v41', 'ppt-master-v42')]
    assert 'motif-libraries/paper-web-v45' in registry
    assert 'motif-libraries/ppt-master-v42' in registry
    for row in candidates:
        assert row['reviewed_changes'] == ['scripts/harless_gateway.mjs']
        assert row['additional_locks'] == ['scripts/reexport-shared-invite-compat.py']
        original = {name: (row['old'] / name).read_bytes() for name in compat.IMMUTABLE_ARTIFACTS}
        stage = frozen_checkout / 'motif-libraries' / ('unpublished-' + row['release'])
        stage.mkdir()
        compat.prepare(row, stage, 'offline-shared-invitation-compatibility-diagnostic')
        assert all((stage / name).read_bytes() == raw for name, raw in original.items())
        record = compat.read(stage / 'learning-report.json')['native_capabilities_compatibility']
        assert record['repairs'] == [
            'explicit_reusable_member_invitation_with_owner_authorized_rotation',
            'concurrent_registration_rechecks_invitation_after_password_hashing']
        assert record['model_requests'] == record['new_training_tasks'] == 0
        assert record['model_task_authority_changed'] is False
        assert record['quality_cost_promoted'] is False
        from src.adapters.harless_rsi_bundle import load_product_bundle
        assert load_product_bundle(frozen_checkout, stage, row['scene'])['runtime_kind'] == row['entry']['runtime_kind']


def test_unreviewed_model_transport_edit_is_rejected(frozen_checkout):
    path = frozen_checkout / 'src/adapters/model_transport.py'
    path.write_bytes(path.read_bytes() + b'\n')
    with pytest.raises(ValueError, match='Exact source review differs'):
        compat.review()


def test_missing_gateway_difference_is_rejected(frozen_checkout):
    remove_expected_difference(compat, frozen_checkout, 'scripts/harless_gateway.mjs')
    with pytest.raises(ValueError, match='Exact source review differs'):
        compat.review()


def test_changed_historical_evidence_is_rejected(frozen_checkout):
    path = frozen_checkout / 'motif-libraries/paper-web-v44/source-evidence.json'
    path.write_bytes(path.read_bytes() + b'\n')
    with pytest.raises(ValueError, match='Previous published artifact changed'):
        compat.review()


def test_existing_destination_is_not_overwritten(frozen_checkout):
    (frozen_checkout / 'motif-libraries/paper-web-v45').mkdir()
    with pytest.raises(ValueError, match='Fresh release path already exists'):
        compat.review()
