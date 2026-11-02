"""Pin actual primitive examples and the C job; no model or generated fixtures."""
import argparse,json,subprocess
from pathlib import Path
from src.adapters.capability_scene import ROOT,reference
from src.adapters.capability_improvement import evidence,save
from src.adapters.capability_contract import create_capability_snapshot
from scenarios.paper_proofreading.frontier.execute import execute
from scenarios.paper_proofreading.frontier.oracle import evaluate,audit,canonical
from scenarios.paper_proofreading.frontier.freeze import protocol_reference


def main():
    p=argparse.ArgumentParser()
    for name in ('base','output','bib_library','tex_library','ledger_root'):p.add_argument('--'+name.replace('_','-'),type=Path,required=True)
    p.add_argument('--store',type=Path)
    p.add_argument('--protocol',type=Path)
    p.add_argument('--owner')
    a=p.parse_args();base=a.base.resolve();protocol,settings,deadline=protocol_reference(base,a.protocol)
    out=a.output.resolve();out.mkdir(parents=True,exist_ok=False)
    owner=a.owner or settings.get('capability_owner') or settings['experiment_id']
    libraries=[reference(a.bib_library.resolve()),reference(a.tex_library.resolve())];catalogs=[]
    for library in libraries:
        r=subprocess.run(['node','scripts/run-script-capability.mjs','--catalog','--library',library['path'],'--owner',owner],cwd=ROOT,capture_output=True,text=True,check=True)
        catalogs.append(json.loads(r.stdout))
    caps=[c for cat in catalogs for c in cat['capabilities']];roots=[r for cat in catalogs for r in cat['roots']]
    seed=create_capability_snapshot(owner,roots,caps);save(out/'seed.json',seed)
    save(out/'catalog.json',{'catalog':[r for c in catalogs for r in c['catalog']]})
    values={};checks=[]
    for project in ('atc','lora'):
        for version in (0,1,2):
            key=f'{project}-v{version}';zip_path=base/'inputs-v1'/(key+'.zip');values[key]={}
            for index,role in enumerate(('bib','tex')):
                trace=execute(catalogs[index]['snapshot'],catalogs[index]['roots'][0],[libraries[index]],
                    [{'path':'/work/inputs/project.zip','source':reference(zip_path)}],{'paths':['/work/inputs/project.zip']},out/'primitive-runs'/key/role,'frontier-'+key+'-'+role)
                value=trace['result']['value'];verdict=evaluate(role,[zip_path],value);checks.append({'input':key,'role':role,'quality':verdict})
                if not verdict['passed']:save(out/'primitive-quality.json',checks);raise ValueError('frontier_primitive_quality_failed')
                values[key][role]=value
    save(out/'primitive-quality.json',checks)
    examples=[];cases=[]
    for project in ('atc','lora'):
        value={'bibliography':values[project+'-v0']['bib'],'latex':values[project+'-v0']['tex']}
        path=out/(project+'-join-input.json');path.write_text(json.dumps(value,ensure_ascii=False,separators=(',',':')))
        examples.append({'input':value,'expected_output':audit(base/'inputs-v1'/(project+'-v0.zip'))})
        cases.append({'id':project+'-C-native','inputs':[{'path':'/work/inputs/value.json','source':reference(path)}]})
    template={'libraries':libraries,'native_cases':{'json':cases},'program_examples':examples,
        'pinned_evidence':[reference(out/'primitive-quality.json')]}
    for label,project in [('validation','atc'),('followup','lora')]:
        template[label]={'id':project+'-C-v1','input':{'project':'/work/inputs/project.zip'},
            'inputs':[{'path':'/work/inputs/project.zip','source':reference(base/'inputs-v1'/(project+'-v1.zip'))}],
            'specification':{'kind':'frontier_literal_v1','role':'C','input_paths':['/work/inputs/project.zip']}}
    save(out/'publication-template.json',template)
    task=settings['tasks']['C'];evidence(task)
    job={'id':'frontier-C','objective':'capability_acquisition','task':task,'publication_plan':reference(out/'publication-template.json'),
        'execution_scope':'frontier-literal-C','source_evidence':[reference(out/'primitive-quality.json')],
        'observations':[{'task_id':'frontier-C-need','kind':'new_requirement','split':'training',
        'summary':'Two certified parsers do not yet join active bibliographies and citations into consistency facts.',
        'evidence':reference(out/'primitive-quality.json')}]}
    dependencies=['adapter.py','author.py','budget.py','learn.py','check.py','publish.mjs','oracle.py']
    plan={'format':'capability_improvement_plan_v1','id':'frontier-C','owner':owner,'output':str(out/'run'),
        'store':str(a.store.resolve() if a.store else out/'store'),'seed':reference(out/'seed.json'),'seed_catalog':reference(out/'catalog.json'),
        'ledger_root':str(a.ledger_root.resolve()),
        'policy':{'version':'capability_improvement_policy_v1','max_repairs':None},'jobs':[job],
        'scene_adapter':reference(Path(__file__).with_name('adapter.py')),
        'scene_dependencies':[reference(Path(__file__).with_name(f)) for f in dependencies]}
    save(out/'plan.json',plan)
    save(out/'request.json',{'plan':reference(out/'plan.json'),'protocol':protocol,
        'cell':'C-acquisition','budget_usd':settings['phase_C_research_budget_usd'],'journal':str(base/'C-request-journal.jsonl'),'deadline':deadline})
    print(json.dumps({'request':reference(out/'request.json'),'primitive_checks':len(checks)}))


if __name__=='__main__':main()
