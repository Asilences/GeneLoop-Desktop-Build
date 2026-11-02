"""Freeze all four D episodes and their initial exposure before any D call."""
import argparse,copy,json,shutil,subprocess
from pathlib import Path
from src.adapters.capability_scene import ROOT,reference
from src.adapters.capability_improvement import evidence,read,save
from src.adapters.capability_contract import create_capability_snapshot,capability_digest
from src.adapters.capability_materials import CapabilityMaterials
from src.adapters.efficiency_rsi_measurement import validate_study
from src.adapters.efficiency_rsi_registry import StudyRequestRegistry
from scenarios.paper_proofreading.frontier.execute import execute
from scenarios.paper_proofreading.frontier.oracle import evaluate,compare


def main():
    parser=argparse.ArgumentParser()
    for name in ('base','output','C_plan','C_run'):parser.add_argument('--'+name.replace('_','-').lower(),type=Path,required=True,dest=name)
    parser.add_argument('--code-commit',required=True)
    a=parser.parse_args();base=a.base.resolve();out=a.output.resolve();out.mkdir(parents=True,exist_ok=False)
    c_plan=read(a.C_plan);c_result=read(a.C_run/'result.json')
    published=[r for r in c_result['outcomes'] if r['status']=='published']
    if len(published)!=1:raise ValueError('frontier_one_published_C_required')
    c_ref=published[0]['capability'];next_paths=list(a.C_run.glob('**/next-library.json'))
    libraries=[read(p) for p in next_paths if c_ref in read(p)['snapshot']['roots']]
    if len(libraries)!=1:raise ValueError('frontier_published_C_library_ambiguous')
    hierarchical=libraries[0]['snapshot'];owner=hierarchical['owner']
    if any(c['implementation']['kind']=='composition' and c['id']!=c_ref['id'] for c in hierarchical['capabilities']):
        raise ValueError('frontier_unexpected_prior_high_level_capability')
    flat=create_capability_snapshot(owner,[r for r in hierarchical['roots'] if r!=c_ref],
        [c for c in hierarchical['capabilities'] if c['id']!=c_ref['id']])
    snapshots={'flat_without_C':flat,'hierarchical_with_C':hierarchical}
    c_template=json.loads(evidence(c_plan['jobs'][0]['publication_plan']))
    native_refs=c_template['libraries']+[r['library'] for r in CapabilityMaterials(Path(c_plan['store'])/'materials',owner).records()]
    native_refs=list({r['sha256']:r for r in native_refs}.values());native_catalog=[]
    for ref in native_refs:
        evidence(ref)
        run=subprocess.run(['node','scripts/run-script-capability.mjs','--catalog','--library',ref['path'],'--owner',owner],
            cwd=ROOT,capture_output=True,text=True,check=True)
        native_catalog.extend(json.loads(run.stdout)['catalog'])
    if {r['capability']['id'] for r in native_catalog}!={r['id'] for r in flat['roots']}:
        raise ValueError('frontier_flat_primitives_do_not_match_C_dependencies')
    training={};checks=[]
    for project in ('atc','lora'):
        for version in (0,1):
            key=f'{project}-v{version}';source=base/'inputs-v1'/(key+'.zip')
            trace=execute(hierarchical,c_ref,native_refs,[{'path':'/work/inputs/project.zip','source':reference(source)}],
                {'project':'/work/inputs/project.zip'},out/'C-training-runs'/key,'frontier-'+key+'-audit')
            value=trace['result'];verdict=evaluate('C',[source],value);checks.append({'input':key,'quality':verdict})
            if not verdict['passed']:save(out/'C-training-quality.json',checks);raise ValueError('frontier_C_training_quality_failed')
            training[key]=value
    save(out/'C-training-quality.json',checks)
    examples=[];cases={'paths':[],'json':[]}
    for project in ('atc','lora'):
        before=base/'inputs-v1'/(project+'-v0.zip');after=base/'inputs-v1'/(project+'-v1.zip')
        value={'before':training[project+'-v0'],'after':training[project+'-v1']}
        path=out/(project+'-D-input.json');path.write_text(json.dumps(value,ensure_ascii=False,separators=(',',':')))
        examples.append({'input':value,'expected_output':compare(before,after)})
        cases['json'].append({'id':project+'-D-json','inputs':[{'path':'/work/inputs/value.json','source':reference(path)}]})
        cases['paths'].append({'id':project+'-D-paths','inputs':[
            {'path':'/work/inputs/before.zip','source':reference(before)},
            {'path':'/work/inputs/after.zip','source':reference(after)}]})
    save(out/'shared-training-examples.json',examples)
    c_task=json.loads(evidence(reference(base/'frozen-v1/task-C.json')))
    task=reference(base/'frozen-v1/task-D.json');protocol=reference(base/'frozen-v1/protocol-server.json')
    source_files=['adapter.py','author.py','budget.py','learn.py','check.py','publish.mjs','oracle.py','execute.py','run.py','prepare_D.py']
    common_files=['src/adapters/capability_scene.py','src/adapters/capability_improvement.py','src/adapters/script_capability_runtime.ts',
        'src/adapters/script_motif_runtime.ts','scripts/certify-script-motifs.mjs','src/adapters/efficiency_rsi_registry.py',
        'src/adapters/efficiency_rsi_measurement.py','config/script-runtime-compatibility.json']
    conditions={'format':'frontier_D_conditions_v1','code_commit':a.code_commit,'protocol':protocol,'task':task,
        'C':published[0],'initial_snapshots':{k:v['digest'] for k,v in snapshots.items()},
        'shared_examples':reference(out/'shared-training-examples.json'),'native_libraries':native_refs,
        'code':[reference(Path(__file__).with_name(f)) for f in source_files]+[reference(ROOT/f) for f in common_files],
        'model':'deepseek-flash','reasoning_effort':'off','max_tokens':393216,'max_output_bytes_per_new_native_program':65536,
        'tools':[],'finite_budget_usd_per_episode':'1.00','outer_attempts_per_cell':1,
        'episode_scope':'All construction proposals, failures, repairs, acquired materials and publication in one episode; initial exposure fixed, intermediate snapshots journaled.',
        'final_test_policy':'Execute QLoRA v0-v1 and v1-v2 only after ALL four construction episodes finish. No final feedback in model calls.',
        'C_acquisition_cost':'Separate phase, including all earlier failed conditions and recovery. Not allocated into conditional D cost or claimed amortized.',
        'Direct_equals_Flat':True,'force_C':False}
    save(out/'conditions.json',conditions)
    (out/'evaluator').mkdir();shutil.copyfile(Path(__file__).with_name('oracle.py'),out/'evaluator/oracle.py')
    arms=[{'id':arm,**{prefix+'_snapshot_sha256':snapshot['digest'] for prefix in ('execution','build')},
        **{prefix+'_capabilities':snapshot['roots'] for prefix in ('execution','build')}} for arm,snapshot in snapshots.items()]
    cells=[{'id':arm+'-r'+str(rep),'task_id':'frontier-D','arm_id':arm,'replicate':rep,'phase':'construction',
        'budget_usd':1.,'max_attempts':1} for rep in (0,1) for arm in snapshots]
    study=validate_study({'format':'efficiency_rsi_study_v1','id':'frontier-D-study-001','objective':'efficiency_and_capability',
        'conditions_sha256':capability_digest(conditions),'rubric_sha256':capability_digest({'required':['heldout_v0_v1','heldout_v1_v2'],'oracle':reference(out/'evaluator/oracle.py')['sha256']}),
        'evaluator':{'id':'frontier-heldout-v1','sha256':reference(out/'evaluator/oracle.py')['sha256'],'ref':'evaluator/oracle.py'},
        'required_checks':['heldout_v0_v1','heldout_v1_v2'],'tasks':[{'id':'frontier-D','sha256':task['sha256'],
        'family':'literal-paper-version-consistency','split':'final_test'}],'arms':arms,'baseline_arm':'flat_without_C','cells':cells,
        'allocation_policy':'explicit_conserved_weights_v1','overhead_allocations':[],
        'budget_policy':'research_comparison_not_platform_authorization','budget_scope':'attempt_execution'})
    save(out/'study.json',study);StudyRequestRegistry(study,out/'study-owner-journal.jsonl',create=True)
    checkpoint=Path(c_plan['ledger_root'])/'budget-checkpoint.json'
    save(out/'ledger-before-D.json',{'checkpoint':read(checkpoint),'ledger_sha256':reference(checkpoint.with_name('cost-ledger.jsonl'))['sha256']})
    requests=[]
    order=[('hierarchical_with_C',0),('flat_without_C',0),('flat_without_C',1),('hierarchical_with_C',1)]
    for arm,rep in order:
        cell=arm+'-r'+str(rep);directory=out/'cells'/cell;directory.mkdir(parents=True)
        save(directory/'seed.json',snapshots[arm])
        catalog=copy.deepcopy(native_catalog)
        if arm=='hierarchical_with_C':catalog.append({'capability':c_ref,'description':c_task['instruction']+
            ' Independently passed ATC and LoRA literal checks; fixed version dependencies; not a general semantic proof.',
            'example_parameters':{'project':'current project ZIP path'}})
        save(directory/'catalog.json',{'catalog':catalog})
        template={'libraries':native_refs,'native_cases':cases,'program_examples':examples,
            'pinned_evidence':[reference(out/'conditions.json'),reference(out/'shared-training-examples.json')]}
        for label,project in [('validation','atc'),('followup','lora')]:
            template[label]={'id':project+'-D-v1-v2','input':{'before':'/work/inputs/before.zip','after':'/work/inputs/after.zip'},
                'inputs':[{'path':'/work/inputs/'+part+'.zip','source':reference(base/'inputs-v1'/f'{project}-v{version}.zip')}
                    for part,version in [('before',1),('after',2)]],
                'specification':{'kind':'frontier_literal_v1','role':'D','input_paths':['/work/inputs/before.zip','/work/inputs/after.zip']}}
        save(directory/'publication-template.json',template)
        job={'id':'frontier-D','objective':'capability_acquisition','task':task,'publication_plan':reference(directory/'publication-template.json'),
            'source_evidence':[reference(out/'shared-training-examples.json')],'execution_scope':'frontier-literal-D',
            'observations':[{'task_id':'frontier-D-training','kind':'new_requirement','split':'training',
                'summary':'Need a reusable cross-version system coupling file and bibliography changes to consistency facts and affected files.',
                'evidence':reference(out/'shared-training-examples.json')}]}
        plan={'format':'capability_improvement_plan_v1','id':cell,'owner':owner,'output':str(directory/'run'),
            'store':str(directory/'store'),'seed':reference(directory/'seed.json'),'seed_catalog':reference(directory/'catalog.json'),
            'ledger_root':c_plan['ledger_root'],'policy':{'version':'capability_improvement_policy_v1','max_repairs':None},'jobs':[job],
            'scene_adapter':reference(Path(__file__).with_name('adapter.py')),
            'scene_dependencies':conditions['code']}
        save(directory/'plan.json',plan)
        save(directory/'request.json',{'plan':reference(directory/'plan.json'),'protocol':protocol,'cell':cell,'budget_usd':'1.00',
            'journal':str(out/'request-journal.jsonl'),'deadline':1793663280.0,
            'study':{'plan':reference(out/'study.json'),'journal':str(out/'study-owner-journal.jsonl'),'episode_id':cell+'-episode'}})
        requests.append(reference(directory/'request.json'))
    save(out/'ordered-requests.json',requests)
    print(json.dumps({'study':reference(out/'study.json'),'order':[r['path'] for r in requests],'C_training_checks':len(checks)}))


if __name__=='__main__':main()
