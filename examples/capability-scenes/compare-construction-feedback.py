"""One isolated historical-task A/B acceptance; original controller and validators.

Fixed task/checkpoint, not autonomous goal discovery or a causal estimate of C.
Default only freezes inputs. --call-model uses the existing cumulative ledger.
"""
import argparse
import copy
from decimal import Decimal
import hashlib
import json
from pathlib import Path
import platform
import subprocess
import sys
import time

ROOT=Path(__file__).resolve().parents[2];sys.path.insert(0,str(ROOT))
from src.adapters.capability_improvement import read,save,evidence,run_improvement
from src.adapters.capability_scene import reference
from src.adapters.capability_construction_history import capture,build_history,amount
from scenarios.paper_proofreading.frontier.adapter import FrontierAdapter
from scenarios.paper_proofreading.frontier.budget import FrontierGate


class AcceptanceAdapter(FrontierAdapter):
    def publish(self,*args):
        result=super().publish(*args)
        # This host uses the unchanged deterministic frontier checker and Script
        # backend. No verifier model is invoked in this specific experiment.
        result.update(model_requests=0,observed_model_usd=0)
        if result['status']=='published':
            result['execution_trace_refs']=[reference(args[2]/'publication'/label/'trace.json')
                for label in ('validation','followup')]
        return result


def prepare(source, prefix, out, budget):
    source=source.resolve();prefix=prefix.resolve();original=read(source)
    if len(original['jobs'])!=1:raise ValueError('acceptance_single_existing_goal_required')
    job=original['jobs'][0];task=json.loads(evidence(job['task']))
    snapshot=json.loads(evidence(original['seed']))
    old=read(prefix/'result.json')
    prefix_snapshot=read(prefix/'snapshot.json')
    if prefix_snapshot['digest']!=snapshot['digest']:
        raise ValueError('acceptance_initial_checkpoint_changed')
    if read(prefix/'task.json')!=task:raise ValueError('acceptance_prefix_task_changed')
    template=json.loads(evidence(job['publication_plan']))
    if any(template[label]['specification']['kind']!='frontier_literal_v1' for label in ('validation','followup')):
        raise ValueError('acceptance_original_deterministic_checker_required')
    # Same training split as current prepare_D; never train on validation/followup.
    if 'construction_cases' not in template:
        template['construction_cases']=[{**copy.deepcopy(case),'split':'training',
            'input':{'before':'/work/inputs/before.zip','after':'/work/inputs/after.zip'}}
            for case in template['native_cases']['paths']]
    save(out/'publication-template.json',template)
    historical=capture(job,prefix,prefix_snapshot,output=out/'prefix-evidence.json')
    save(out/'prefix-history.json',build_history([historical],job['task']))
    plans={}
    for arm in ('A','B'):
        directory=out/arm;directory.mkdir(mode=0o700)
        plan=copy.deepcopy(original)
        plan.update(id='creation-feedback-'+arm,output=str(directory/'run'),store=str(directory/'store'),
            feedback_directory=str(directory/'feedback'),
            scene_adapter=reference(ROOT/'scenarios/paper_proofreading/frontier/adapter.py'),
            scene_dependencies=[reference(ROOT/'scenarios/paper_proofreading/frontier'/name)
                for name in ('author.py','check.py','oracle.py','publish.mjs')])
        plan['policy']['max_repairs']=2
        plan['jobs'][0]['publication_plan']=reference(out/'publication-template.json')
        if arm=='B':plan['construction_feedback']={'max_reconsiderations':1,'history':[historical]}
        save(directory/'plan.json',plan);plans[arm]=plan
    save(out/'frozen.json',{'format':'creation_feedback_acceptance_v1',
        'source_plan':reference(source),'prefix_result':reference(prefix/'result.json'),
        'prefix_historical_cost_usd_decimal':old.get('observed_model_usd_decimal'),
        'prefix_cost_scope':'Common historical evidence, not newly billed or claimed as savings',
        'initial_snapshot_sha256':snapshot['digest'],'task':job['task'],
        'new_budget_usd_per_arm':str(budget),'aggregate_new_budget_usd':str(2*budget),
        'model':'deepseek-flash','reasoning_effort':'off','max_tokens':393216,
        'execution_order':['A','B'],'tool_order':[],
        'difference':'B consumes prior/full construction history and permits one reconsideration after repair stops',
        'quality':'Original independent checks, no goal algorithm or mandatory predecessor supplied',
        'scope':'Historical checkpoint acceptance; not new user/project generalization or C causal value',
        'python':sys.version,'os':platform.platform(),
        'node':subprocess.check_output(['node','--version'],text=True).strip(),
        'runner_sha256':hashlib.sha256(Path(__file__).read_bytes()).hexdigest()})
    return plans,snapshot


def run(plans,snapshot,out,budget):
    report={'status':'running','arms':{},'creation_efficiency':None,'C_causal_value':None}
    save(out/'started.json',{'time':time.time(),'scope':'New directory, no automatic resume/replay'})
    with FrontierGate(plans['A']['ledger_root'],out/'research-requests.jsonl',deadline=time.time()+2700) as gate:
        report['cumulative_before']={'requests':gate.state.request_count,'accounted_usd':gate.state.reserved_usd}
        for arm,plan in plans.items():
            gate.activate(arm,str(budget));adapter=AcceptanceAdapter(plan);adapter.gate=gate
            try:result=run_improvement(plan,adapter,execute=True)
            except Exception as error:result={'status':'failed','error':type(error).__name__+':'+str(error)}
            keys=[key for key,cell in gate.request_cells.items() if cell==arm]
            costs=[gate.exact_costs.get(key) for key in keys]
            total=sum(costs,Decimal(0)) if all(cost is not None for cost in costs) else None
            attempts=[];C=[c['id'] for c in snapshot['capabilities'] if c['implementation']['kind']=='composition']
            for folder in sorted(Path(plan['output']).glob('**/attempt-*')):
                if not folder.is_dir() or not (folder/'result.json').is_file():continue
                record=read(folder/'result.json');traces=[]
                for trace_path in sorted((folder/'publication').glob('*/trace.json')):
                    trace=read(trace_path)
                    traces.append({'trace':reference(trace_path),'status':trace.get('status'),
                        'successful_C_calls':sum(row.get('status')=='succeeded' and
                            row.get('capability',{}).get('id') in C for row in trace.get('receipts',[]))})
                attempts.append({'path':str(folder),'result':reference(folder/'result.json'),
                    'status':record['status'],'error':record.get('error'),
                    'strategy':read(folder/'strategy.json') if (folder/'strategy.json').is_file() else None,
                    'runtime_traces':traces})
            report['arms'][arm]={'controller':result,'provider_requests':len(keys),
                'observed_model_usd_decimal':None if total is None else str(total),'attempts':attempts,
                'requests':[{'request_id':rid,'ledger_ref':str(gate.root/'cost-ledger.jsonl'),
                    'usage':gate.completed.get(rid,{}).get('response_usage'),
                    'observed_model_usd_decimal':None if gate.exact_costs.get(rid) is None else str(gate.exact_costs[rid])} for rid in keys]}
            save(out/(arm+'-result.json'),report['arms'][arm])
        report['cumulative_after']={'requests':gate.state.request_count,'accounted_usd':gate.state.reserved_usd}
    report['status']='completed';save(out/'result.json',report)
    print(json.dumps({'status':report['status'],'arms':{arm:{key:row[key] for key in (
        'provider_requests','observed_model_usd_decimal')} for arm,row in report['arms'].items()}}))


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--source-plan',type=Path,required=True)
    parser.add_argument('--prefix-attempt',type=Path,required=True)
    parser.add_argument('--output',type=Path,required=True)
    parser.add_argument('--budget-usd',required=True)
    parser.add_argument('--call-model',action='store_true')
    args=parser.parse_args();out=args.output.resolve();budget=amount(args.budget_usd)
    if budget is None:parser.error('finite research budget required')
    if not out.is_relative_to(ROOT/'.local'):parser.error('private output required')
    out.mkdir(parents=True,exist_ok=False,mode=0o700)
    plans,snapshot=prepare(args.source_plan,args.prefix_attempt,out,budget)
    if args.call_model:run(plans,snapshot,out,budget)
    else:print(json.dumps({'status':'frozen_preview','model_requests':0}))


if __name__=='__main__':main()
