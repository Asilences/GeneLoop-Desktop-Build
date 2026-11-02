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
