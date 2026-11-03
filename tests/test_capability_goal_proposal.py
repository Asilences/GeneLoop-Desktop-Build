"""Single-turn protocol diagnostics only; no real provider calls."""
import json
from decimal import Decimal
from types import SimpleNamespace
from contextlib import contextmanager

from src.adapters.capability_goal_proposal import propose
from tests.test_capability_proposal_loop import DiagnosticGate, fake_harness


class FiniteDiagnosticGate(DiagnosticGate):
    budget=SimpleNamespace(limit=Decimal('2.00'))
    def register_attempt(self,path,owner,*,category):self.registered=(path,owner,category)


def test_single_goal_turn_preserves_request_ownership_and_native_configuration(tmp_path,monkeypatch):
    goal={'need_id':'open','proposed_goal':'A relevant next capability','expected_dependencies':[],
          'reason':'Unmet user need'}
    observed=fake_harness(monkeypatch,json.dumps({'goals':[goal]}),notifications=True)
    gate=FiniteDiagnosticGate()
    result=propose({'owner':'owner','trigger_id':'frozen-update','max_candidates':2},tmp_path/'proposal',gate)
    assert result['status']=='proposed' and result['goals']==[goal]
    assert result['request_ids']==[123] and result['observed_model_usd'] is None
    assert gate.current is None and gate.registered[2]=='goal_discovery'
    assert observed['model']=='deepseek-flash' and observed['max_tokens']==393216
    assert (tmp_path/'proposal/answer.txt').exists() and (tmp_path/'proposal/events.jsonl').exists()


def test_incomplete_goal_turn_retains_fees_and_does_not_retry(tmp_path,monkeypatch):
    fake_harness(monkeypatch,'incomplete answer',complete=False)
    gate=FiniteDiagnosticGate()
    result=propose({'owner':'owner','trigger_id':'update'},tmp_path/'failed',gate)
    assert result['status']=='failed' and result['goals']==[] and result['request_ids']==[123]
    assert (tmp_path/'failed/answer.txt').read_text()=='incomplete answer'
    assert gate.current is None


def test_public_adapter_opens_and_closes_finite_gate_only_for_goal_turn(tmp_path,monkeypatch):
    from src.adapters.capability_scene import CapabilityImprovementAdapter
    fake_harness(monkeypatch,json.dumps({'goals':[]}))
    adapter=CapabilityImprovementAdapter.__new__(CapabilityImprovementAdapter);events=[]
    @contextmanager
    def factory(request,output):
        events.append('opened')
        try:yield FiniteDiagnosticGate()
        finally:events.append('closed')
    adapter.opportunity_gate_factory=factory
    result=adapter.propose_opportunities({'owner':'owner','trigger_id':'update'},tmp_path/'one-turn')
    assert result['status']=='proposed' and events==['opened','closed']
