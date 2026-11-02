"""Initial L0 primitive construction; real model, then actual native admission."""
import argparse,json,sys
from pathlib import Path
from src.adapters.capability_scene import reference,ROOT
from src.adapters.capability_improvement import save,evidence
from scenarios.paper_proofreading.frontier.author import propose
from scenarios.paper_proofreading.frontier.budget import FrontierGate
from scenarios.paper_proofreading.frontier.learn import learn


def main():
    p=argparse.ArgumentParser();p.add_argument('--request',type=Path,required=True);a=p.parse_args()
    request=json.loads(a.request.read_text());out=Path(request['output']);out.mkdir(parents=True,exist_ok=False)
    task=json.loads(evidence(request['task']));catalog=json.loads(evidence(request['catalog']))
    library={'snapshot':catalog['snapshot'],'source_catalog':catalog}
    with FrontierGate(request['ledger_root'],request.get('journal',out/'request-journal.jsonl'),deadline=request['deadline']) as gate:
        gate.activate('C-acquisition',request['budget_usd'])
        result=propose(task=task,library=library,output=out/'attempt-0',gate=gate,owner_id=request['id']+'/attempt-0')
    save(out/'model-result.json',result)
    if not result.get('program_request'):raise ValueError('frontier_source_program_not_proposed')
    program=json.loads(Path(result['program_request']).read_text())
    try:
        ref=learn(program,request['native_cases'],out/'native',reference(out/'attempt-0/answer.txt'),large_output=request.get('large_output',False))
        outcome={'status':'certified','library':ref,'model_requests':result['provider_requests']}
    except Exception as error:outcome={'status':'deferred','error':str(error),'model_requests':result['provider_requests']}
    save(out/'result.json',outcome);print(json.dumps(outcome))


if __name__=='__main__':main()
