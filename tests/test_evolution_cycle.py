"""A second minimal adapter verifies portability, not autonomous improvement."""
import json
from pathlib import Path

from src.adapters.capability_contract import capability_ref, create_capability_snapshot
from src.adapters.capability_feedback import file_ref, verify
from src.adapters.evolution_cycle import run_evolution_cycle
from tests.test_capability_contract import leaf
from tests.test_capability_investigation import data, make, put
from tests.test_capability_evolution_investigation import candidate


def test_second_adapter_routes_its_receiver_and_accumulates_new_capability_and_experience(tmp_path, data):
    class DiagnosticAdapter:
        def load_experiences(self):
            return make(tmp_path, data)

        def build_receivers(self):
            def receive(value, context, directory):
                self.received = value
                return {'status': 'pending', 'reason': 'diagnostic receiver; no empirical certification'}
            return {'construction_strategy': receive}

        def evaluate_followup(self, result):
            row = {'task_id': 'independent-diagnostic-task', 'source_identity': 'independent-diagnostic-source',
                'relation': 'changed-process', 'stage': 'execution', 'status': 'passed',
                'capabilities': [capability_ref(self.new_capability)], 'evidence': [], 'observed_cost_usd': None}
            ref = put(tmp_path / 'successor.json', row)
            return {'entries': [{'split': 'training', 'scope': 'study', 'evidence': ref}],
                    'inspector': lambda reference, owner: json.loads(verify(reference)),
                    'result': {'diagnostic_only': True, 'actual_adoption': None}}

        def current_capabilities(self):
            self.new_capability = {**leaf('next', data[0]['owner']), 'certification': 'certified', 'lifecycle': 'active'}
            return create_capability_snapshot(data[0]['owner'],
                [*data[0]['roots'], capability_ref(self.new_capability)], [*data[0]['capabilities'], self.new_capability])

    adapter = DiagnosticAdapter()
    # The evaluator normally obtains this from the original Store. The fixture
    # builds it before the callback so no candidate controls a certification.
    latest = adapter.current_capabilities()
    def agent(request, dispatch):
        cards = dispatch('evolution_search', {'kind': 'experience'})['items']
        dispatch('evolution_submit', {'candidate': candidate([row['id'] for row in cards[:2]]),
                                     'observation_ids': [row['id'] for row in cards[:2]]})
        dispatch('evolution_finish', {'decision': 'proposal', 'reason': 'Diagnostic routing completed'})
        return {}
    result, next_view = run_evolution_cycle(adapter.load_experiences(), call_agent=agent,
        handlers=adapter.build_receivers(), output=tmp_path / 'cycle',
        limits={'max_tool_calls': 10, 'timeout_seconds': 10},
        followup_evaluator=adapter.evaluate_followup, load_current_capabilities=lambda: latest)
    assert adapter.received['kind'] == 'construction_strategy'
    assert result['supported_receivers'] == ['construction_strategy']
    assert next_view.snapshot == latest and len(next_view.observations) == 4
    assert next_view.overview()['capabilities']['selectable'] == 3
    assert result['actual_adoption'] is None and result['diagnostic_only'] is True


def test_cycle_no_change_needs_no_followup_and_preserves_revisit_identity(tmp_path, data):
    def finish(request, dispatch):
        dispatch('evolution_finish', {'decision': 'no_change', 'reason': 'Retain the method in this diagnostic'})
        return {}
    first, view = run_evolution_cycle(make(tmp_path, data), call_agent=finish, handlers={},
        output=tmp_path / 'first', limits={'max_tool_calls': 5, 'timeout_seconds': 10})
    def forbidden(*_): raise AssertionError('unchanged evidence should not issue another request')
    second, next_view = run_evolution_cycle(view, call_agent=forbidden, handlers={},
        output=tmp_path / 'second', limits={'max_tool_calls': 5, 'timeout_seconds': 10},
        prior_results=[file_ref(tmp_path / 'first/agent/result.json')])
    assert first['status'] == 'no_change' and second['status'] == 'revisit_skipped'
    assert next_view.snapshot == data[0] and len(next_view.observations) == 3


def test_shared_cycle_has_no_scene_specific_import_or_scoring():
    from src.adapters import evolution_cycle
    source = Path(evolution_cycle.__file__).read_text()
    for text in ('BibTeX', 'paper_proofreading', 'QLoRA', 'score ==', 'BenchmarkHost'):
        assert text not in source
