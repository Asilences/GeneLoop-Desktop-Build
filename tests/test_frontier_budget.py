"""Admission diagnostics: all attempts share one finite research cell budget."""
from decimal import Decimal as D
import pytest
from scenarios.paper_proofreading.frontier.budget import ResearchBudget


def test_complete_spend_not_first_attempt_controls_later_admission():
    b=ResearchBudget('1');b.book(1,D('.6'));assert not b.available(D('.5'))
    b.finish(1,D('.1'));assert b.available(D('.9'))
    b.book(2,D('.9'));b.finish(2,D('.2'))
    assert b.available(D('.7')) and not b.available(D('.7000000001'))


def test_unknown_request_keeps_upper_reservation_and_no_budget_reset():
    b=ResearchBudget('1');b.book(1,D('.8'));b.finish(1,None)
    assert b.spent==D('.8') and not b.available(D('.3'))
    with pytest.raises(ValueError):b.book(2,D('.3'))


def test_reopening_runner_preserves_known_and_unsettled_costs(tmp_path):
    import json,time
    from scenarios.paper_proofreading.frontier.budget import FrontierGate
    p=tmp_path/'journal.jsonl'
    rows=[{'event':'cell_activated','cell':'c','budget_usd':'1'},
          {'event':'request_booked','cell':'c','request_id':7,'reserved_upper_usd':'.6'},
          {'event':'request_settled','cell':'c','request_id':7,'observed_model_usd':'.1'},
          {'event':'request_booked','cell':'c','request_id':8,'reserved_upper_usd':'.6'}]
    p.write_text(''.join(json.dumps(r)+'\n' for r in rows),encoding='utf-8')
    gate=FrontierGate(tmp_path,p,deadline=time.time()+60);gate.activate('c','1')
    assert gate.budget.spent==D('.1') and gate.budget.pending=={8:D('.6')}
    assert gate.budget.available(D('.3')) and not gate.budget.available(D('.3000000001'))
    with pytest.raises(ValueError,match='budget_changed'):FrontierGate(tmp_path,p,deadline=time.time()+60).activate('c','2')
