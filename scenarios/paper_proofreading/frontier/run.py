"""Execute one pre-registered cell; paid requests use the shared finite gate."""
import argparse,json
from decimal import Decimal,InvalidOperation
from pathlib import Path
from src.adapters.capability_improvement import evidence,run_improvement
from src.adapters.capability_contract import validate_capability_snapshot
from scenarios.paper_proofreading.frontier.adapter import FrontierAdapter
from scenarios.paper_proofreading.frontier.budget import FrontierGate,StudyEpisodeRegistry
from src.adapters.efficiency_rsi_registry import StudyRequestRegistry
from scenarios.paper_proofreading.frontier.freeze import deadline_epoch


def validate_request(request,plan,protocol,study=None):
    """Reject changed research conditions before any owner registration or fee."""
    if type(request.get('deadline')) not in (int,float) or request['deadline']!=deadline_epoch(protocol['deadline_utc']):
        raise ValueError('frontier_request_deadline_changed')
    def budget(value):
        try:amount=Decimal(str(value))
        except InvalidOperation as error:raise ValueError('frontier_research_budget_invalid') from error
        if not amount.is_finite() or amount<0:raise ValueError('frontier_research_budget_invalid')
        return amount
    actual=budget(request['budget_usd'])
    if study is None:
        if actual!=budget(protocol['phase_C_research_budget_usd']):raise ValueError('frontier_request_budget_changed')
        return None
    cells=[c for c in study['cells'] if c['id']==request['cell']]
    if len(cells)!=1 or plan['id']!=request['cell']:raise ValueError('frontier_request_cell_changed')
    cell=cells[0]
    if actual!=budget(cell['budget_usd']):raise ValueError('frontier_request_budget_changed')
    arm=next(a for a in study['arms'] if a['id']==cell['arm_id'])
    seed=validate_capability_snapshot(json.loads(evidence(plan['seed'])),plan['owner'])
    if seed['digest']!=arm['build_snapshot_sha256']:raise ValueError('frontier_study_initial_exposure_changed')
    task=next(t for t in study['tasks'] if t['id']==cell['task_id'])
    if len(plan['jobs'])!=1 or plan['jobs'][0]['task']['sha256']!=task['sha256']:
        raise ValueError('frontier_study_task_changed')
    return arm['build_snapshot_sha256']


def main():
    p=argparse.ArgumentParser();p.add_argument('--request',type=Path,required=True);a=p.parse_args()
    request=json.loads(a.request.read_text());plan=json.loads(evidence(request['plan']))
    protocol=json.loads(evidence(request['protocol']))
    for ref in protocol['evaluator_files']:evidence(ref)
    study_plan=json.loads(evidence(request['study']['plan'])) if request.get('study') else None
    expected=validate_request(request,plan,protocol,study_plan)
    adapter=FrontierAdapter(plan)
    if expected is not None:
        if adapter.library()['snapshot']['digest']!=expected:raise ValueError('frontier_study_initial_exposure_changed')
        adapter.expected_initial_snapshot_sha256=expected
    registry=None
    if request.get('study'):
        study=request['study'];formal=StudyRequestRegistry(study_plan,study['journal'])
        registry=StudyEpisodeRegistry(formal,plan['output'],study['episode_id'],request['cell'])
    with FrontierGate(plan['ledger_root'],request['journal'],deadline=request['deadline'],study_registry=registry) as gate:
        gate.activate(request['cell'],request['budget_usd']);adapter.gate=gate
        print(json.dumps(run_improvement(plan,adapter,execute=True),ensure_ascii=False))


if __name__=='__main__':main()
