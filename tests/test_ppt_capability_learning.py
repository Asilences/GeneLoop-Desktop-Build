"""Synthetic normal-task admission diagnostics; model/cost claims require real runs."""
import json
from pathlib import Path
import pytest
from tests.test_web_ppt_learning import owned, task, single, worker
from src.adapters.ppt_capability_learning import sync_ppt_capabilities
from scenarios.ppt_master.capability_adapter import PptCapabilityAdapter
from src.adapters.capability_scene import reference
from src.adapters.capability_discovery import discover_jobs
from src.adapters.ppt_program_learning import read, save


def test_real_worker_projects_single_normal_tasks_without_comparison_or_model(owned):
    output, store, request = owned
    (output / 'comparisons.json').unlink()
    for index in (1, 2):
        single(owned, task(owned, index))
    worker.advance(request)
    status = read(store / 'capability/status.json')
    assert status['status'] == 'waiting_for_native_certification'
    assert len(status['observations']) == 2
    assert not (output / 'comparisons.json').exists()
    for proof in status['observations']:
        record = read(Path(proof['path']))
        assert record['owner'] == 'diagnostic-user'
        assert record['quality'] == 'mechanical_delivery_scientific_and_visual_unknown'
        assert record['trace']['benefit'] is None


def test_public_discovery_uses_the_same_single_task_evidence_and_rejects_owner_or_tampering(owned):
    output, store, request = owned
    (output / 'comparisons.json').unlink()
    for index in (1, 2):
        single(owned, task(owned, index))
    worker.advance(request)
    status = read(store / 'capability/status.json')
    publication = store / 'publication.json';save(publication, {'diagnostic': True})
    context = store / 'context.json'
    save(context, {'owner': 'diagnostic-user', 'scope': 'a' * 64, 'contract': {'input_schema': {'type': 'object'},
         'output_schema': {'type': 'object'}, 'effects': ['workspace_write']}, 'publication_plan': reference(publication)})
    adapter = object.__new__(PptCapabilityAdapter)
    entries = [{'kind': 'ppt_normal_task', 'run': str(Path(ref['path']).parent), 'role': 'training', 'context': reference(context)}
               for ref in status['observations']]
    jobs = discover_jobs(entries, 'diagnostic-user', store / 'discovery', inspector=adapter.inspect_run)
    assert len(jobs) == 1 and len(jobs[0]['observations']) == 2
    with pytest.raises(ValueError, match='context_invalid'):
        adapter.inspect_run(entries[0], 'other')
    with pytest.raises(ValueError, match='scope_invalid'):
        adapter.inspect_run({**entries[0], 'role': 'heldout'}, 'diagnostic-user')
    record = read(Path(status['observations'][0]['path']))
    Path(record['evidence'][0]['path']).write_text('tampered', encoding='utf-8')
    with pytest.raises(ValueError, match='evidence_changed'):
        adapter.inspect_run(entries[0], 'diagnostic-user')


def test_failed_or_heldout_single_tasks_are_excluded(owned):
    output, store, request = owned
    for index in (1, 2):
        directory = task(owned, index);single(owned, directory)
        if index == 1:
            state = read(directory / 'task-state.json');state['failure'] = 'diagnostic failure';save(directory / 'task-state.json', state)
        else:
            value = read(directory / 'task.json');value['learning_eligible'] = False;save(directory / 'task.json', value)
    worker.advance(request)
    assert read(store / 'capability/status.json')['observations'] == []
