"""Common scene improvement entry; host adapter code is pinned, preview by default."""
import argparse,json,signal,sys
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT))
from src.adapters.capability_improvement import read,run_improvement,validate
from src.adapters.capability_scene import load_scene_adapter


def main():
    def interrupted(signum,frame):raise KeyboardInterrupt('improvement_interrupted')
    signal.signal(signal.SIGTERM,interrupted)
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--plan',type=Path,required=True)
    parser.add_argument('--call-model',action='store_true')
    parser.add_argument('--execute',action='store_true',help='Execute only frozen learned candidates, without a model proposal')
    args=parser.parse_args();plan=validate('plan',read(args.plan))
    if args.execute and (args.call_model or not plan['jobs'] or any(not j.get('learned_candidate') for j in plan['jobs'])
                         or any(plan.get(k) for k in ('discovery','opportunity_discovery','learning_routes'))):
        parser.error('--execute requires only frozen learned-candidate jobs and no discovery/model/learning routes')
    if not Path(plan['output']).resolve().is_relative_to(ROOT/'.local'):
        parser.error('raw improvement evidence must remain in private .local')
    if plan.get('opportunity_discovery') and not Path(plan['opportunity_discovery']['directory']).resolve().is_relative_to(ROOT/'.local'):
        parser.error('opportunity evidence must remain in private .local')
    adapter=load_scene_adapter(plan)
    result=run_improvement(plan,adapter,execute=args.call_model or args.execute)
    print(json.dumps(result,ensure_ascii=False))
    if result['status'] not in ('completed','preview'):raise SystemExit(1)


if __name__=='__main__':main()
