"""Execute one pre-registered cell; paid requests use the shared finite gate."""
import argparse,json
from pathlib import Path
from src.adapters.capability_improvement import evidence,run_improvement
from scenarios.paper_proofreading.frontier.adapter import FrontierAdapter
from scenarios.paper_proofreading.frontier.budget import FrontierGate,StudyEpisodeRegistry
from src.adapters.efficiency_rsi_registry import StudyRequestRegistry


def main():
    p=argparse.ArgumentParser();p.add_argument('--request',type=Path,required=True);a=p.parse_args()
    request=json.loads(a.request.read_text());plan=json.loads(evidence(request['plan']))
    protocol=json.loads(evidence(request['protocol']))
    for ref in protocol['evaluator_files']:evidence(ref)
    adapter=FrontierAdapter(plan)
    registry=None
    if request.get('study'):
        study=request['study'];formal=StudyRequestRegistry(json.loads(evidence(study['plan'])),study['journal'])
        registry=StudyEpisodeRegistry(formal,plan['output'],study['episode_id'],request['cell'])
    with FrontierGate(plan['ledger_root'],request['journal'],deadline=request['deadline'],study_registry=registry) as gate:
        gate.activate(request['cell'],request['budget_usd']);adapter.gate=gate
        print(json.dumps(run_improvement(plan,adapter,execute=True),ensure_ascii=False))


if __name__=='__main__':main()
