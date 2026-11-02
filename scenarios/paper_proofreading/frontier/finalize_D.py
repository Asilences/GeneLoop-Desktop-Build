"""Evaluate frozen candidates AFTER every D episode, then close and measure.

No model calls. No held-out outcome is returned to an improvement controller.
Unpublished interface/search failures remain unresolved rather than supporting
an inference about the model's fundamental capability boundary.
"""
import argparse,json,time
from decimal import Decimal
from pathlib import Path
from src.adapters.capability_scene import ROOT,reference
from src.adapters.capability_improvement import evidence,read,save
from src.adapters.capability_contract import capability_digest
from src.adapters.capability_materials import CapabilityMaterials
from src.adapters.efficiency_rsi_registry import StudyRequestRegistry
from src.adapters.efficiency_rsi_measurement import measure_study,digest as study_digest
from src.adapters.rsi_protocol import envelope
from scenarios.paper_proofreading.frontier.execute import execute
from scenarios.paper_proofreading.frontier.oracle import evaluate,sha


def main():
    p=argparse.ArgumentParser();p.add_argument('--directory',type=Path,required=True);p.add_argument('--base',type=Path,required=True)
    p.add_argument('--evaluation-id',default='evaluation-001');a=p.parse_args()
    if not a.evaluation_id.replace('-','').isalnum():raise ValueError('frontier_evaluation_id_invalid')
    directory=a.directory.resolve();base=a.base.resolve();study=read(directory/'study.json');conditions=read(directory/'conditions.json')
    if capability_digest(conditions)!=study['conditions_sha256']:raise ValueError('frontier_D_conditions_changed')
    for ref in conditions['code']:evidence(ref)
    protocol=json.loads(evidence(conditions['protocol']))
    for ref in protocol['evaluator_files']:evidence(ref)
    if reference(Path(__file__).with_name('oracle.py'))['sha256']!=study['evaluator']['sha256']:raise ValueError('frontier_final_evaluator_changed')
    requests=[json.loads(evidence(ref)) for ref in read(directory/'ordered-requests.json')]
    plans=[json.loads(evidence(r['plan'])) for r in requests]
    if any(not (Path(plan['output'])/'result.json').exists() for plan in plans):raise ValueError('frontier_all_episodes_must_finish_before_final_test')
    journal=[json.loads(line) for line in (directory/'request-journal.jsonl').read_text().splitlines()]
    books={r['request_id']:r for r in journal if r['event']=='request_booked'}
    settled={r['request_id']:r for r in journal if r['event']=='request_settled'}
    ledger=Path(plans[0]['ledger_root'])/'cost-ledger.jsonl';lines=ledger.read_bytes().splitlines(keepends=True)
    terminal={}
    for line in lines:
        row=json.loads(line)
        if row.get('request_id') in books:terminal[row['request_id']]=row
    if set(terminal)!=set(books):raise ValueError('frontier_D_provider_inventory_incomplete')
    first=next((i for i,line in enumerate(lines) if json.loads(line).get('request_id') in books),len(lines))
    if sha(b''.join(lines[:first]))!=read(directory/'ledger-before-D.json')['ledger_sha256']:raise ValueError('frontier_prior_cumulative_ledger_changed')
    registry=StudyRequestRegistry(study,directory/'study-owner-journal.jsonl')
    refs=[{'ledger_ref':r['ledger_ref'],'id':str(rid)} for rid,r in books.items()]
    provisional=registry.export(refs)
    result_dir=directory/a.evaluation_id;result_dir.mkdir(exist_ok=False)
    attempts=[];details=[];providers=[]
    arms={r['id']:r for r in study['arms']};cells={r['id']:r for r in study['cells']}
    for request,plan in zip(requests,plans):
        cell=request['cell'];arm=arms[cells[cell]['arm_id']];run=Path(plan['output']);construction=read(run/'result.json')
        published=[r for r in construction['outcomes'] if r['status']=='published'];quality=None
        status='completed' if conditions.get('format')=='frontier_D_conditions_v2' else 'environment_error'
        local=result_dir/cell;local.mkdir();cell_details={'cell':cell,'construction':construction,'final_cases':[]}
        if published:
            if len(published)!=1:raise ValueError('frontier_D_publication_ambiguous')
            root=published[0]['capability'];candidates=[read(p) for p in run.glob('**/next-library.json') if root in read(p)['snapshot']['roots']]
            if len(candidates)!=1:raise ValueError('frontier_D_frozen_candidate_ambiguous')
            snapshot=candidates[0]['snapshot'];template=json.loads(evidence(plan['jobs'][0]['publication_plan']))
            libraries=template['libraries']+[r['library'] for r in CapabilityMaterials(Path(plan['store'])/'materials',plan['owner']).records()]
            checks=[];execution_errors=False
            projects=conditions.get('final_projects') or [{'id':'heldout','versions':{str(i):reference(base/'inputs-v1'/f'qlora-v{i}.zip') for i in range(3)}}]
            cases=[(project,before,after) for project in projects for before,after in [(0,1),(1,2)]]
            for project,before,after in cases:
                label=f"{project['id']}_v{before}_v{after}";case_dir=local/label
                inputs=[{'path':'/work/inputs/'+part+'.zip','source':project['versions'][str(version)]}
                    for part,version in [('before',before),('after',after)]]
                started=time.monotonic();trace=None
                try:
                    trace=execute(snapshot,root,libraries,inputs,{'before':'/work/inputs/before.zip','after':'/work/inputs/after.zip'},case_dir,cell+'-'+label)
                    verdict=evaluate('D',[Path(i['source']['path']) for i in inputs],trace['result'])
                except Exception as error:
                    execution_errors=True;verdict={'passed':False,'execution_error':str(error),'checks':[]}
                    if (case_dir/'trace.json').exists():
                        try:trace=read(case_dir/'trace.json')
                        except ValueError:pass
                save(case_dir/'quality.json',verdict)
                file=reference(case_dir/'quality.json');file['ref']=str(Path(file.pop('path')).relative_to(directory))
                checks.append({'id':label,'status':'unknown' if 'execution_error' in verdict else 'passed' if verdict['passed'] else 'failed',
                    'observation':'Actual frozen native result compared with independent oracle; '+('execution unavailable' if 'execution_error' in verdict else str(verdict['passed'])),
                    'evidence':[file]})
                calls=[] if trace is None else [r for r in trace.get('receipts',[]) if r.get('capability')==conditions['C']['capability']]
                relations=[] if trace is None or not conditions.get('J') else [r for r in trace.get('receipts',[]) if r.get('capability')==conditions['J']]
                cell_details['final_cases'].append({'case':label,'quality':verdict,'native_elapsed_seconds':time.monotonic()-started,
                    'C_calls':[{'call_id':r['call_id'],'parent_call_id':r.get('parent_call_id'),'status':r['status']} for r in calls],
                    'J_calls':[{'call_id':r['call_id'],'parent_call_id':r.get('parent_call_id'),'status':r['status']} for r in relations]})
            status='environment_error' if execution_errors else 'completed'
            if not execution_errors:cell_details['quality_checks']=checks
            cell_details['C_selected']=conditions['C']['capability'] in next(c for c in snapshot['capabilities'] if c['id']==root['id'])['dependencies']
        else:
            cell_details['limitation']='No published candidate after interface/search failures. Held-out execution unavailable; no capability-unlock or savings inference.'
        save(local/'artifact.json',cell_details);artifact=reference(local/'artifact.json');artifact_ref=str((local/'artifact.json').relative_to(directory))
        if published and status=='completed':
            quality=envelope('quality_evaluation',{'id':cell+'-quality','task_id':'frontier-D','task_sha256':study['tasks'][0]['sha256'],
                'artifact_sha256':artifact['sha256'],'rubric_sha256':study['rubric_sha256'],'evaluator':study['evaluator']['id'],
                'scope':'Literal held-out project version consistency; two controlled transitions per project',
                'limitations':['No TeX expansion or factual review','Controlled source changes','One held-out project, not independent projects per transition'],
                'checks':cell_details['quality_checks']})
        owned=[rid for rid,r in books.items() if r['cell']==cell]
        starts=[r['time'] for r in journal if r['event']=='owner_registered' and r['cell']==cell]
        attempts.append({'id':request['study']['episode_id'],'cell_id':cell,'ordinal':1,'parent_attempt_id':None,
            'conditions_sha256':study['conditions_sha256'],**{k:arm[k] for k in ('execution_snapshot_sha256','build_snapshot_sha256','execution_capabilities','build_capabilities')},
            'status':status,'request_refs':[{'ledger_ref':books[rid]['ledger_ref'],'id':str(rid)} for rid in owned],
            'artifact_ref':artifact_ref,'artifact_sha256':artifact['sha256'],'quality':quality,
            'wall_seconds':max(0,time.time()-min(starts)) if starts else None})
        details.append(cell_details)
        for rid in owned:
            cost=settled.get(rid,{}).get('observed_model_usd')
            if cost is not None and terminal[rid].get('response_status')!=200:raise ValueError('frontier_D_cost_response_mismatch')
            providers.append({'ledger_ref':books[rid]['ledger_ref'],'id':str(rid),'phase':'completed' if cost is not None else 'failed',
                'observed_peak_usd':float(Decimal(cost)) if cost is not None else None,
                'reserved_upper_usd':float(Decimal(books[rid]['reserved_upper_usd'])),'allocations':{cells[cell]['arm_id']:1.}})
    obs={'format':'efficiency_rsi_observations_v1','plan_sha256':study_digest(study),'registry_sha256':study_digest(provisional),
        'attempts':attempts,'overheads':[],'providers':providers}
    # Validate all evidence before mutating the registry's closure state.
    measure_study(study,obs,registry=provisional,evidence_root=directory)
    closed={r['cell_id'] for r in provisional['cells'] if r['closed']}
    for cell in study['cells']:
        if cell['id'] not in closed:registry.close_cell(cell['id'])
    frozen=registry.export(refs);obs['registry_sha256']=study_digest(frozen)
    report=measure_study(study,obs,registry=frozen,evidence_root=directory)
    for name,value in [('registry',frozen),('observations',obs),('measurement',report),('details',details),
                       ('usage',[{'request_id':rid,'cell':books[rid]['cell'],'usage':terminal[rid].get('response_usage')} for rid in books])]:save(result_dir/(name+'.json'),value)
    print(json.dumps({'measurement':reference(result_dir/'measurement.json'),'physical_cost':report['physical_study_cost'],
        'cells':[{k:r[k] for k in ('id','outcome')} for r in report['cells']]}))


if __name__=='__main__':main()
