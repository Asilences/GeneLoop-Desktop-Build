"""Zero-model event replay using frozen real project evidence and prior proposals.

This checks plumbing, not autonomous goal discovery or new efficiency gains.
The original algorithms, inputs, validators and source runs remain unchanged.
"""
import argparse
import copy
import json
from pathlib import Path
import sys

ROOT=Path(__file__).resolve().parents[2];sys.path.insert(0,str(ROOT))
from src.adapters.capability_improvement import evidence,read,save,run_improvement
from src.adapters.capability_scene import CapabilityImprovementAdapter,reference
from src.adapters.capability_builder import compile_proposal
from src.adapters.capability_contract import capability_ref,create_capability_snapshot,capability_digest
from scenarios.paper_proofreading.frontier.adapter import FrontierAdapter


class ReplayAdapter(CapabilityImprovementAdapter):
    def freeze_publication_inputs(self,job):
        template=json.loads(evidence(job['publication_plan']))
        for ref in template['libraries']:evidence(ref)
        for label in ('validation','followup'):
            for item in template[label]['inputs']:evidence(item['source'])
        return template

    def construct(self,task,library,output,parent,feedback):
        output.mkdir(mode=0o700)
        original=self.c if task['contract']==self.c['contract'] else self.d
        if task['contract']!=original['contract']:raise ValueError('replay_contract_changed')
        proposal={'format':'capability_compose_proposal_v1','owner':self.plan['owner'],
            'contract':copy.deepcopy(original['contract']),
            'steps':copy.deepcopy(original['implementation']['steps']),
            'output':copy.deepcopy(original['implementation']['output'])}
        candidate=compile_proposal(proposal,library['snapshot'],self.plan['owner'])
        save(output/'proposal.json',proposal);save(output/'candidate.json',candidate)
        result={'status':'compiled_candidate','model_called':False,'provider_requests':0,
            'observed_model_usd':0,'observed_model_usd_decimal':'0',
            'construction_snapshot_sha256':library['snapshot']['digest'],
            'scope':'Replay of prior model algorithms, not a new autonomous construction'}
        save(output/'result.json',result);return result

    def publish(self,*args):
        outcome=FrontierAdapter.publish(self,*args)
        trace=args[2]/'publication/validation/trace.json'
        if outcome['status']=='published':outcome['execution_trace_refs']=[reference(trace)]
        return outcome

    def propose_opportunities(self,request,output):
        return {'status':'diagnostic_replay','goals':[{'need_id':'project-maintenance',
            'proposed_goal':self.d_task['instruction'],'expected_dependencies':request['newly_visible'],
            'reason':'Frozen diagnostic proposal for an existing real project requirement'}],
            'model_called':False,'request_ids':[],'observed_model_usd':0,'diagnostic_only':True}

    def review_opportunity(self,proposal,request,directory):
        # Independent conditions are frozen host files; never supplied by the proposal.
        task=copy.deepcopy(self.d_task)
        if proposal['proposed_goal']!=task['instruction']:
            return {'decision':'pending','reason':'No frozen checker for this goal'}
        task_path=directory/'host-D-task.json';save(task_path,task)
        review=directory/'host-review.json'
        save(review,{'scope':'Frozen independent validation/followup on real project copies',
            'source_task':self.d_task_ref,'publication_plan':self.d_template_ref})
        return {'decision':'accepted','evidence':reference(review),'job':{
            'id':'host-reviewed','objective':'capability_acquisition','execution_scope':request['task_scope'],
            'task':reference(task_path),'publication_plan':self.d_template_ref,
            'observations':[{'task_id':'project-maintenance','kind':'new_requirement','split':'training',
                'summary':'Existing cross-version maintenance requirement','evidence':self.d_task_ref}]}}


def main():
    p=argparse.ArgumentParser()
    for key in ('c-plan','c-attempt','d-plan','d-attempt','output'):
        p.add_argument('--'+key,type=Path,required=True)
    a=p.parse_args();out=a.output.resolve()
    if not out.is_relative_to(ROOT/'.local'):p.error('replay artifacts must remain in private .local')
    out.mkdir(parents=True,exist_ok=False,mode=0o700)
    cp,dp=read(a.c_plan),read(a.d_plan)
    cc,dc=read(a.c_attempt/'candidate.json'),read(a.d_attempt/'candidate.json')
    owner=cc['capability']['owner']
    if dc['capability']['owner']!=owner:raise ValueError('replay_owner_changed')
    source_refs=[reference(path) for path in (a.c_plan,a.d_plan,a.c_attempt/'candidate.json',a.d_attempt/'candidate.json')]
    save(out/'source-evidence.json',{'refs':source_refs,'model_requests':0,
        'scope':'Real public paper sources and prior model proposals; fixed goals/algorithms for event diagnosis only'})
    templates=[json.loads(evidence(plan['jobs'][0]['publication_plan'])) for plan in (cp,dp)]
    libraries=read(a.d_attempt/'publication-plan.json')['validation']['manifest']['libraries']
    template_refs=[]
    for label,template in zip(('C','D'),templates):
        value={key:copy.deepcopy(template[key]) for key in ('validation','followup')};value['libraries']=libraries
        save(out/(label+'-validation.json'),value);template_refs.append(reference(out/(label+'-validation.json')))
    native=[cap for cap in dc['snapshot']['capabilities'] if cap['implementation']['kind']=='legacy']
    seed=create_capability_snapshot(owner,[capability_ref(cap) for cap in native],native)
    save(out/'seed.json',seed);save(out/'catalog.json',{})
    ctask=read(a.c_attempt/'task.json');dtask=read(a.d_attempt/'task.json')
    save(out/'C-task.json',ctask);save(out/'D-task.json',dtask)
    context={'format':'capability_opportunity_context_v1','owner':owner,'task_scope':'real-project-maintenance',
        'allowed_effects':['read'],'needs':[{'id':'project-maintenance','description':'Maintain consistency as the existing project changes',
            'status':'open','evidence':[reference(out/'source-evidence.json'),reference(out/'D-task.json')]}]}
    save(out/'context.json',context)
    job={'id':'replay-C','objective':'capability_acquisition','task':reference(out/'C-task.json'),
        'publication_plan':template_refs[0],'observations':[{'task_id':'real-project-maintenance',
        'kind':'new_requirement','split':'training','summary':'Prior project consistency requirement','evidence':reference(out/'source-evidence.json')}]}
    plan={'format':'capability_improvement_plan_v1','id':'opportunity-real-evidence-replay','owner':owner,
        'output':str(out/'run'),'store':str(out/'store'),'seed':reference(out/'seed.json'),
        'seed_catalog':reference(out/'catalog.json'),'ledger_root':str(out/'unused-no-model-ledger'),
        'policy':{'version':'capability_improvement_policy_v1','max_repairs':0},'jobs':[job],
        'opportunity_discovery':{'context':reference(out/'context.json'),'directory':str(out/'goals'),
            'max_reconsiderations':1,'max_candidates':2}}
    save(out/'plan.json',plan)
    adapter=ReplayAdapter(plan);adapter.c=cc['capability'];adapter.d=dc['capability']
    adapter.d_task=dtask;adapter.d_task_ref=reference(out/'D-task.json');adapter.d_template_ref=template_refs[1]
    result=run_improvement(plan,adapter,execute=True)
    save(out/'summary.json',{'result':result,'model_requests':0,'diagnostic_only':True,
        'scope':'Existing real-project algorithms replayed through capability-update goal selection, Builder, Runtime and independent publication'})
    print(json.dumps({'status':result['status'],'outcomes':result['outcomes'],'model_requests':0}))
    if [row['status'] for row in result['outcomes']]!=['published','published']:raise SystemExit(1)


if __name__=='__main__':main()
