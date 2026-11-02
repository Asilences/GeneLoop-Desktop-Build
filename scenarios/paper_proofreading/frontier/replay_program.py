"""Zero-model diagnosis of a saved program and its mechanical task wrapper."""
import argparse,copy,json,subprocess
from pathlib import Path
from src.adapters.capability_scene import ROOT,reference
from src.adapters.capability_improvement import evidence,save
from src.adapters.capability_contract import create_capability_snapshot
from src.adapters.capability_program_encoding import encode_complete_script
from scenarios.paper_proofreading.frontier.learn import learn
from scenarios.paper_proofreading.frontier.adapter import FrontierAdapter


def main():
    p=argparse.ArgumentParser();p.add_argument('--request',type=Path,required=True);a=p.parse_args()
    request=json.loads(a.request.read_text());out=Path(request['output']);out.mkdir(parents=True,exist_ok=False)
    program=json.loads(evidence(request['program']));task=json.loads(evidence(request['task']))
    template=json.loads(evidence(request['publication_template']));seed=json.loads(evidence(request['seed']))
    try:
        library=request.get('native_library') or learn(program,template['native_cases'][program['mode']],out/'native',request['program'],large_output=True)
        observations=request.get('native_observations') or reference(out/'native/observations.json')
        evidence(library);evidence(observations)
        native=subprocess.run(['node','scripts/run-script-capability.mjs','--catalog','--library',library['path'],'--owner',seed['owner']],
            cwd=ROOT,capture_output=True,text=True,check=True)
        mapped=json.loads(native.stdout);caps={c['id']:c for c in [*seed['capabilities'],*mapped['capabilities']]}
        roots={r['id']:r for r in [*seed['roots'],*mapped['roots']]};snapshot=create_capability_snapshot(seed['owner'],list(roots.values()),list(caps.values()))
        encoded=encode_complete_script(task,snapshot,library,observations)
        if encoded is None:raise ValueError('frontier_program_not_mechanically_complete')
        attempt=out/'encoding';attempt.mkdir();save(attempt/'proposal.json',encoded['proposal']);save(attempt/'candidate.json',encoded['candidate'])
        save(attempt/'provenance.json',{'model_requests_this_replay':0,'scope':encoded['encoding_scope'],
            'original_program':request['program'],'native_library':library,'native_observations':observations})
        if library not in template['libraries']:template['libraries'].append(library)
        save(out/'publication-template.json',template);save(out/'seed.json',snapshot);save(out/'catalog.json',{'catalog':mapped['catalog']})
        job={'id':'saved-program-replay','objective':'capability_acquisition','task':request['task'],
            'observations':[],'publication_plan':reference(out/'publication-template.json'),'source_evidence':[request['program']]}
        plan={'format':'capability_improvement_plan_v1','id':'zero-model-program-replay','owner':seed['owner'],
            'store':str(out/'store'),'output':str(out/'unused-controller-output'),'ledger_root':str(out/'unused-ledger'),
            'seed':reference(out/'seed.json'),'seed_catalog':reference(out/'catalog.json'),
            'policy':{'version':'capability_improvement_policy_v1','max_repairs':0},'jobs':[job]}
        adapter=FrontierAdapter(plan);outcome=adapter.publish(job,encoded['candidate'],attempt,None)
        result={'model_requests':0,'original_program':request['program'],'native_library':library,'outcome':outcome,
            'scope':'Host encoded an unchanged prior model solver; not a new autonomous construction experiment'}
    except Exception as error:result={'model_requests':0,'status':'failed','error':str(error),'scope':'Saved program diagnosis'}
    save(out/'result.json',result);print(json.dumps(result))


if __name__=='__main__':main()
