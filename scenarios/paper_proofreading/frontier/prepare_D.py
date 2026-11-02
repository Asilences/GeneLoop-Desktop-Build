"""Freeze D episodes and their initial exposure before any D call."""
import argparse,copy,json,re,shutil,subprocess
from decimal import Decimal,InvalidOperation
from pathlib import Path
from src.adapters.capability_scene import ROOT,reference
from src.adapters.capability_improvement import evidence,read,save
from src.adapters.capability_contract import create_capability_snapshot,capability_digest
from src.adapters.capability_materials import CapabilityMaterials
from src.adapters.efficiency_rsi_measurement import validate_study
from src.adapters.efficiency_rsi_registry import StudyRequestRegistry
from scenarios.paper_proofreading.frontier.execute import execute
from scenarios.paper_proofreading.frontier.oracle import evaluate,compare
from scenarios.paper_proofreading.frontier.freeze import protocol_reference


def subset(snapshot,roots):
    caps={c['id']:c for c in snapshot['capabilities']};selected={};todo=list(roots)
    while todo:
        ref=todo.pop()
        if ref['id'] in selected:continue
        selected[ref['id']]=caps[ref['id']];todo.extend(caps[ref['id']]['dependencies'])
    return create_capability_snapshot(snapshot['owner'],roots,list(selected.values()))


def structural_schema(value):
    if isinstance(value,dict):return {'type':'object','properties':{k:structural_schema(v) for k,v in value.items()},'required':list(value),'additionalProperties':False}
    if isinstance(value,list):return {'type':'array',**({'items':structural_schema(value[0])} if value else {})}
    return {'type':'null' if value is None else 'boolean' if isinstance(value,bool) else 'number' if isinstance(value,(int,float)) else 'string'}


def read_journal(path):
    raw=Path(path).read_text(encoding='utf-8')
    if not raw.endswith('\n'):raise ValueError('frontier_prior_journal_incomplete')
    return [json.loads(line) for line in raw.splitlines()]


def finite_budget(value):
    try:amount=Decimal(str(value))
    except InvalidOperation as error:raise ValueError('frontier_research_budget_invalid') from error
    if not amount.is_finite() or amount<0:raise ValueError('frontier_research_budget_invalid')
    return str(amount)


def load_final_projects(manifest_paths):
    """Pin supplied projects without executing a candidate or filtering quality.

    Legacy manifests used array order as the version and omitted the project ID.
    New manifests may name versions explicitly, in any order.
    """
    projects=[];ids=set()
    for raw_path in manifest_paths:
        path=Path(raw_path).resolve();manifest_ref=reference(path);manifest=json.loads(evidence(manifest_ref))
        if not isinstance(manifest,dict):raise ValueError('frontier_final_versions_invalid')
        project_id=manifest.get('id','mamba')
        if not isinstance(project_id,str) or not re.fullmatch(r'[A-Za-z0-9][A-Za-z0-9_-]{0,63}',project_id) or project_id in ids:
            raise ValueError('frontier_final_project_id_invalid')
        rows=manifest.get('versions');versions={};sources=set()
        if not isinstance(rows,list) or len(rows)!=3:raise ValueError('frontier_final_versions_invalid')
        for index,row in enumerate(rows):
            if not isinstance(row,dict):raise ValueError('frontier_final_versions_invalid')
            version=row.get('version',index)
            if type(version) is not int or version not in (0,1,2) or str(version) in versions:
                raise ValueError('frontier_final_versions_invalid')
            name=row.get('file');digest=row.get('sha256')
            if not isinstance(name,str) or not name or '\\' in name or '\x00' in name:
                raise ValueError('frontier_final_source_path_invalid')
            relative=Path(name)
            if relative.is_absolute() or '..' in relative.parts:raise ValueError('frontier_final_source_path_invalid')
            source=(path.parent/relative).resolve()
            if not source.is_relative_to(path.parent) or source in sources or not source.is_file():
                raise ValueError('frontier_final_source_path_invalid')
            if not isinstance(digest,str) or not re.fullmatch(r'[0-9a-f]{64}',digest):
                raise ValueError('frontier_fresh_final_inputs_changed')
            ref=reference(source)
            if ref['sha256']!=digest:raise ValueError('frontier_fresh_final_inputs_changed')
            versions[str(version)]=ref;sources.add(source)
        ids.add(project_id)
        projects.append({'id':project_id,'versions':{str(i):versions[str(i)] for i in range(3)},'source_manifest':manifest_ref})
    if not projects:raise ValueError('frontier_v2_fresh_final_manifest_required')
    return projects


def final_project_checks(projects):
    return [project['id']+suffix for project in projects for suffix in ('_v0_v1','_v1_v2')]


def freeze_research_budget(budget,limit,cell_count,prior_journals):
    prior={};settled={}
    for path in prior_journals:
        for row in read_journal(path):
            if row['event']=='request_booked':prior[row['request_id']]=Decimal(row['reserved_upper_usd'])
            elif row['event']=='request_settled':settled[row['request_id']]=row['observed_model_usd']
    accounted=sum((Decimal(settled[rid]) if settled.get(rid) is not None else reserve for rid,reserve in prior.items()),Decimal(0))
    upper=accounted+Decimal(finite_budget(budget))*cell_count
    limit=finite_budget(limit)
    if upper>Decimal(limit):raise ValueError('frontier_aggregate_research_budget_exceeded')
    value={'prior_accounted_upper_usd':str(accounted),'aggregate_planned_upper_usd':str(upper),
           'aggregate_model_estimate_limit_usd':limit}
    if prior_journals:value['prior_research_journals']=[reference(Path(p).resolve()) for p in prior_journals]
    return value


def main():
    parser=argparse.ArgumentParser()
    for name in ('base','output','C_plan','C_run'):parser.add_argument('--'+name.replace('_','-').lower(),type=Path,required=True,dest=name)
    parser.add_argument('--code-commit',required=True)
    parser.add_argument('--v2',action='store_true');parser.add_argument('--final-manifest',type=Path,action='append',default=[])
    parser.add_argument('--task-file',type=Path);parser.add_argument('--study-name')
    parser.add_argument('--protocol',type=Path)
    parser.add_argument('--prior-journal',type=Path,action='append',default=[])
    parser.add_argument('--budget-usd');parser.add_argument('--research-limit-usd',default='6.00')
    a=parser.parse_args();base=a.base.resolve();protocol,settings,deadline=protocol_reference(base,a.protocol)
    budget=finite_budget(a.budget_usd if a.budget_usd is not None else ('0.80' if a.v2 else '1.00'))
    research_limit=finite_budget(a.research_limit_usd)
    final_projects=load_final_projects(a.final_manifest) if a.v2 else None
    out=a.output.resolve();out.mkdir(parents=True,exist_ok=False)
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
    relation=None
    if a.v2:
        base_refs=[r['capability'] for r in native_catalog if r['input_contracts'] and all(c['format']=='zip' for c in r['input_contracts'])]
        relations=[r['capability'] for r in native_catalog if 'value' in r['input_schema'].get('properties',{})]
        if len(base_refs)!=2 or len(relations)!=1:raise ValueError('frontier_v2_vocabulary_partition_invalid')
        relation=relations[0]
        snapshots={'direct_L0':subset(hierarchical,base_refs),
            'flat_without_C':subset(hierarchical,[*base_refs,relation]),
            'hierarchical_with_C':subset(hierarchical,[*base_refs,relation,c_ref])}
        hierarchical=snapshots['hierarchical_with_C']
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
    c_task=json.loads(evidence(settings['tasks']['C']))
    task=reference(a.task_file.resolve()) if a.task_file else settings['tasks']['D'];evidence(task)
    source_files=['adapter.py','author.py','budget.py','learn.py','check.py','publish.mjs','oracle.py','execute.py','run.py','prepare_D.py','finalize_D.py','feedback.py','freeze.py']
    common_files=['src/adapters/capability_scene.py','src/adapters/capability_improvement.py','src/adapters/capability_authoring.py','src/adapters/capability_composition_source.py','src/adapters/script_capability_runtime.ts',
        'src/adapters/script_motif_runtime.ts','scripts/certify-script-motifs.mjs','src/adapters/efficiency_rsi_registry.py',
        'src/adapters/efficiency_rsi_measurement.py','config/script-runtime-compatibility.json',
        'src/adapters/script_motif_compiler.py','src/adapters/capability_program_encoding.py']
    presentation={'schema_only_examples':True,'hide_composition_definitions':True,'hide_redundant_JSON_file_variants':True} if a.v2 else {}
    conditions={'format':'frontier_D_conditions_v1','code_commit':a.code_commit,'protocol':protocol,'task':task,
        'C':published[0],'initial_snapshots':{k:v['digest'] for k,v in snapshots.items()},
        'shared_examples':reference(out/'shared-training-examples.json'),'native_libraries':native_refs,
        'code':[reference(Path(__file__).with_name(f)) for f in source_files]+[reference(ROOT/f) for f in common_files],
        'model':'deepseek-flash','reasoning_effort':'off','max_tokens':393216,'max_output_bytes_per_new_native_program':65536,
        'tools':[],'finite_budget_usd_per_episode':budget,'outer_attempts_per_cell':1,
        'episode_scope':'All construction proposals, failures, repairs, acquired materials and publication in one episode; initial exposure fixed, intermediate snapshots journaled.',
        'final_test_policy':'Execute QLoRA v0-v1 and v1-v2 only after ALL four construction episodes finish. No final feedback in model calls.',
        'C_acquisition_cost':'Separate phase, including all earlier failed conditions and recovery. Not allocated into conditional D cost or claimed amortized.',
        'Direct_equals_Flat':not a.v2,'force_C':False,'presentation':presentation,'auto_wrap_complete_program':a.v2}
    required_checks=['heldout_v0_v1','heldout_v1_v2'];baseline='flat_without_C'
    if a.v2:
        conditions.update(format='frontier_D_conditions_v2',J=relation,
            contrasts=[['direct_L0','flat_without_C'],['flat_without_C','hierarchical_with_C'],['direct_L0','hierarchical_with_C']],
            final_projects=final_projects,
            final_test_policy='All six episodes finish before final project tests; no final feedback in model calls.')
        required_checks=final_project_checks(final_projects);baseline='direct_L0'
    conditions.update(freeze_research_budget(budget,research_limit,len(snapshots)*2,a.prior_journal))
    save(out/'conditions.json',conditions)
    (out/'evaluator').mkdir();shutil.copyfile(Path(__file__).with_name('oracle.py'),out/'evaluator/oracle.py')
    arms=[{'id':arm,**{prefix+'_snapshot_sha256':snapshot['digest'] for prefix in ('execution','build')},
        **{prefix+'_capabilities':snapshot['roots'] for prefix in ('execution','build')}} for arm,snapshot in snapshots.items()]
    cells=[{'id':arm+'-r'+str(rep),'task_id':'frontier-D','arm_id':arm,'replicate':rep,'phase':'construction',
        'budget_usd':float(budget),'max_attempts':1} for rep in (0,1) for arm in snapshots]
    study=validate_study({'format':'efficiency_rsi_study_v1','id':a.study_name or ('frontier-D-study-002' if a.v2 else 'frontier-D-study-001'),'objective':'efficiency_and_capability',
        'conditions_sha256':capability_digest(conditions),'rubric_sha256':capability_digest({'required':required_checks,'oracle':reference(out/'evaluator/oracle.py')['sha256']}),
        'evaluator':{'id':'frontier-heldout-v1','sha256':reference(out/'evaluator/oracle.py')['sha256'],'ref':'evaluator/oracle.py'},
        'required_checks':required_checks,'tasks':[{'id':'frontier-D','sha256':task['sha256'],
        'family':'literal-paper-version-consistency','split':'final_test'}],'arms':arms,'baseline_arm':baseline,'cells':cells,
        'allocation_policy':'explicit_conserved_weights_v1','overhead_allocations':[],
        'budget_policy':'research_comparison_not_platform_authorization','budget_scope':'attempt_execution'})
    save(out/'study.json',study);StudyRequestRegistry(study,out/'study-owner-journal.jsonl',create=True)
    checkpoint=Path(c_plan['ledger_root'])/'budget-checkpoint.json'
    save(out/'ledger-before-D.json',{'checkpoint':read(checkpoint),'ledger_sha256':reference(checkpoint.with_name('cost-ledger.jsonl'))['sha256']})
    requests=[]
    order=[('hierarchical_with_C',0),('flat_without_C',0),('flat_without_C',1),('hierarchical_with_C',1)]
    if a.v2:order=[('hierarchical_with_C',0),('flat_without_C',0),('direct_L0',0),('direct_L0',1),('flat_without_C',1),('hierarchical_with_C',1)]
    for arm,rep in order:
        cell=arm+'-r'+str(rep);directory=out/'cells'/cell;directory.mkdir(parents=True)
        save(directory/'seed.json',snapshots[arm])
        visible={r['id'] for r in snapshots[arm]['roots']}
        catalog=copy.deepcopy([r for r in native_catalog if r['capability']['id'] in visible])
        c_description=('Callable project citation audit: accepts a current project ZIP path in project and returns root, files (current byte hashes and tex/bib kind), includes, bibliography, citations, active entries, missing, duplicates, unused and unresolved. It follows reachable literal LaTeX input/include and bibliography edges, joins ONLY active bibliography entries to citations, preserves duplicate records and computes the three key sets. It does not expand macros or judge factual bibliography truth.' if a.v2 else c_task['instruction'])
        if arm=='hierarchical_with_C':catalog.append({'capability':c_ref,'description':c_description+
            ' Independently passed ATC and LoRA literal checks; fixed version dependencies; not a general semantic proof.',
            'example_parameters':{'project':'current project ZIP path'}})
        save(directory/'catalog.json',{'catalog':catalog})
        template={'libraries':native_refs,'native_cases':cases,'program_examples':examples,
            'pinned_evidence':[reference(out/'conditions.json'),reference(out/'shared-training-examples.json')],
            'auto_wrap_complete_program':a.v2,'presentation':presentation,
            'program_input_schemas':{'json':structural_schema(examples[0]['input']),
                'paths':{'type':'object','properties':{key:{'type':'string','description':'Current granted project ZIP path; read geneloop-project.json root'} for key in ('before','after')},'required':['before','after'],'additionalProperties':False}} if a.v2 else {}}
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
        save(directory/'request.json',{'plan':reference(directory/'plan.json'),'protocol':protocol,'cell':cell,'budget_usd':budget,
            'journal':str(out/'request-journal.jsonl'),'deadline':deadline,
            'study':{'plan':reference(out/'study.json'),'journal':str(out/'study-owner-journal.jsonl'),'episode_id':cell+'-episode'}})
        requests.append(reference(directory/'request.json'))
    save(out/'ordered-requests.json',requests)
    print(json.dumps({'study':reference(out/'study.json'),'order':[r['path'] for r in requests],'C_training_checks':len(checks)}))


if __name__=='__main__':main()
