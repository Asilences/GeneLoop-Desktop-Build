"""Execute one pre-registered cell; paid requests use the shared finite gate."""
import argparse,json
from pathlib import Path
from src.adapters.capability_improvement import evidence,run_improvement
from scenarios.paper_proofreading.frontier.adapter import FrontierAdapter
from scenarios.paper_proofreading.frontier.budget import FrontierGate


def main():
    p=argparse.ArgumentParser();p.add_argument('--request',type=Path,required=True);a=p.parse_args()
    request=json.loads(a.request.read_text());plan=json.loads(evidence(request['plan']))
    protocol=json.loads(evidence(request['protocol']))
    for ref in protocol['evaluator_files']:evidence(ref)
    adapter=FrontierAdapter(plan)
    with FrontierGate(plan['ledger_root'],request['journal'],deadline=request['deadline']) as gate:
        gate.activate(request['cell'],request['budget_usd']);adapter.gate=gate
        print(json.dumps(run_improvement(plan,adapter,execute=True),ensure_ascii=False))


if __name__=='__main__':main()
