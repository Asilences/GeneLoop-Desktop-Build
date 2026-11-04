"""Real Runtime/Store wiring with synthetic native authority, no model claims."""
import copy
import json
from pathlib import Path

import pytest

from src.adapters import capability_program_training as training
from src.adapters.capability_contract import capability_digest, capability_ref, create_capability_snapshot
from src.adapters.capability_motif_learning import capture_composition_trace, learn_capability_motifs, _at
from tests.test_capability_composition_projection import nested, run
from tests.test_capability_motif_learning import put


def native(snapshot,root,libraries,inputs,args,directory,task_id,*,mode):
    """Actual Runtime with explicitly synthetic Script-shaped grant envelope."""
    directory.mkdir(parents=True)
    registry=put(directory/'snapshot.json',snapshot)
    grant={'id':'rae-validation-'+task_id,'task_id':task_id,'snapshot_sha256':snapshot['digest'],
        'root':root,'arguments_sha256':capability_digest(args),'mode':mode,'effects':['read'],'revoked':False}
    manifest={'format':'script_capability_task_v1','task_id':task_id,'owner':snapshot['owner'],
        'workspace':str(directory),'registry_path':registry['path'],'libraries':libraries,'inputs':[], 'grant':grant}
    ref=put(directory/'manifest.json',manifest);put(directory/'args.json',args)
    execution=run({'snapshot':snapshot,'root':root,'input':args,'task_id':task_id,'mode':mode})['execution']
    execution.update(format='script_capability_trace_v1',grant_id=grant['id'],validation_grant_id=grant['id'],
        manifest_sha256=ref['sha256'],input_versions=[])
    put(directory/'trace.json',execution)
    assert execution['status']=='succeeded'
    return execution


def prepare(tmp_path,snapshot,original_root,case_values,*,config=None,label='training',case_inputs=None):
    task={'id':label,'instruction':'Prepare inputs for the requested helper', 'contract':original_root['contract']}
    program={'source':'def run(value):\n    return value\n','description':'Synthetic requested helper',
             'mode':'json','interface':'function_v1'}
    intent={'format':'capability_program_composition_intent_v1','owner':snapshot['owner'],
        'construction_snapshot_sha256':snapshot['digest'],'task_sha256':capability_digest(task),'program_sha256':capability_digest(program),
        'steps':[*original_root['implementation']['steps'],{'id':'new_helper','capability':'$program',
            'arguments':{'kind':'object','fields':{'value':original_root['implementation']['output']}}}],
        'output':{'kind':'step','step_id':'new_helper','path':[]}}
    directory=tmp_path/label;directory.mkdir()
    cases=[{'id':label+'-'+str(i),'split':'training','input':{'before':before,'after':after},
            'inputs':[] if case_inputs is None else case_inputs[i]}
           for i,(before,after) in enumerate(case_values)]
    result=training.prepare_program_cases(task,snapshot,put(directory/'program.json',program),put(directory/'intent.json',intent),
        cases,[],directory/'prepared',builder_learning=config)
    record=json.loads(Path(result['evidence']['path']).read_text(encoding='utf-8'))
    return record


@pytest.fixture
def observed(tmp_path,nested,monkeypatch):
    snapshot,_,traces=nested
    original_root=next(cap for cap in snapshot['capabilities'] if cap['id']==
        json.loads(Path(traces[0]['execution_ref']['path']).read_text())['root']['id'])
    monkeypatch.setattr(training,'execute',native)
    first=prepare(tmp_path,snapshot,original_root,[('old','new'),('empty','same')],config={'enabled':True})
    later=prepare(tmp_path,snapshot,original_root,[('independent','empty'),('heldout','other')],
                  config={'enabled':True},label='heldout')
    refs=[case['builder_trajectory'] for record in (first,later) for case in record['cases']]
    projections=[json.loads(Path(ref['path']).read_text(encoding='utf-8')) for ref in refs]
    learned=learn_capability_motifs(projections[:2],projections[2:3],snapshot)
    assert len(learned['candidates'])==1
    return snapshot,original_root,first,refs,projections,learned['candidates'][0]


def published_selection(tmp_path,observed):
    snapshot,root,first,refs,projections,learned=observed
    assert all(row['role']=='builder' and row['container_certification']=='candidate' for row in projections)
    assert all(any(c['certification']=='candidate' for c in row['snapshot']['capabilities']) for row in projections)
    # Two distinct heldout preparation inputs feed the unchanged Store cycle.
    cases=[]
    for trace in projections[2:]:
        window=trace['steps'][1:]
        args={binding['input_name']:_at(window[binding['step_index']]['arguments'],binding['argument_path'])
              for binding in learned['provenance']['source_input_bindings']}
        cases.append((args,window[-1]['result']))
    published=run({'action':'publish','compiled':learned['compiled'],'seed':snapshot,'directory':str(tmp_path/'store'),
        'validation_input':cases[0][0],'expected_validation':cases[0][1],
        'followup_input':cases[1][0],'expected_followup':cases[1][1]})
    assert published['result']['followup_passed'] is True
    current=published['library']['snapshot'];ref=capability_ref(learned['compiled']['capability'])
    config={'enabled':True,'selection':{'root':ref,'candidate':put(tmp_path/'learned.json',learned),'source_trace':refs[0]}}
    return current,config


def test_actual_preparation_calls_are_learned_published_and_used_in_later_preparation(tmp_path,observed):
    current,config=published_selection(tmp_path,observed);root=observed[1];ref=config['selection']['root']
    result=prepare(tmp_path,current,root,[('future-before','future-after'),('another','empty')],config=config,label='successor')
    assert result['builder_learning']['status']=='selected'
    assert all(row['builder_application']=='learned_prefix' for row in result['cases'])
    for case in result['cases']:
        trace=json.loads(Path(case['builder_trajectory']['path']).read_text(encoding='utf-8'))
        assert len(trace['steps'])==2 and trace['steps'][-1]['capability']==ref
        assert json.loads(Path(case['value']['path']).read_text())==trace['steps'][-1]['result']['value']


@pytest.mark.parametrize('change',['grant','mode','owner','input','snapshot','revoked','manifest_bytes','library','visibility'])
def test_candidate_container_requires_frozen_host_validation_and_visible_certified_children(tmp_path,observed,change):
    snapshot,_,_,_,projections,_=observed
    projection=projections[0];execution=json.loads(Path(projection['execution_ref']['path']).read_text())
    manifest=json.loads(Path(projection['validation_manifest_ref']['path']).read_text());available=snapshot
    if change=='grant':manifest['grant']['id']='another'
    elif change=='mode':manifest['grant']['mode']='execute'
    elif change=='owner':manifest['owner']='foreign'
    elif change=='input':manifest['grant']['arguments_sha256']='0'*64
    elif change=='snapshot':manifest['grant']['snapshot_sha256']='0'*64
    elif change=='revoked':manifest['grant']['revoked']=True
    elif change=='manifest_bytes':manifest['workspace']+='-changed'
    elif change=='library':manifest['libraries']=[{'path':str(tmp_path/'absent-library'),'sha256':'0'*64}]
    elif change=='visibility':
        hidden=projection['steps'][0]['capability']
        available=create_capability_snapshot(snapshot['owner'],[ref for ref in snapshot['roots'] if ref!=hidden],snapshot['capabilities'])
    manifest_ref=put(tmp_path/'changed-manifest.json',manifest)
    if change!='manifest_bytes':execution['manifest_sha256']=manifest_ref['sha256']
    execution_ref=put(tmp_path/'changed-trace.json',execution)
    with pytest.raises((ValueError,OSError)):
        capture_composition_trace(projection['snapshot'],execution_ref=execution_ref,
            task_input=projection['execution_input'],task_fingerprint=projection['task_fingerprint'],role='builder',
            validation_manifest_ref=manifest_ref,available_snapshot=available)


def test_unpublished_selection_falls_back_and_disabled_does_not_read_it(tmp_path,observed):
    snapshot,root,_,refs,_,learned=observed
    selection={'root':capability_ref(learned['compiled']['capability']),
        'candidate':put(tmp_path/'candidate.json',learned),'source_trace':refs[0]}
    fallback=prepare(tmp_path,snapshot,root,[('a','b'),('c','d')],config={'enabled':True,'selection':selection},label='fallback')
    assert fallback['builder_learning']['status']=='fallback'
    assert 'selection_unavailable' in fallback['builder_learning']['error']
    assert all(case['builder_application']=='original_prefix' for case in fallback['cases'])
    selection['candidate']['path']=str(tmp_path/'does-not-exist')
    disabled=prepare(tmp_path,snapshot,root,[('a','b'),('c','d')],config={'enabled':False,'selection':selection},label='disabled')
    assert 'builder_learning' not in disabled
    assert all('builder_trajectory' not in case for case in disabled['cases'])


def test_reordered_same_input_evidence_is_not_two_builder_training_cases(tmp_path,observed,monkeypatch):
    snapshot,root,*_=observed
    files=[{'path':'/work/inputs/'+name+'.json','source':put(tmp_path/(name+'.json'),{'name':name})} for name in ('a','b')]
    monkeypatch.setattr(training,'execute',lambda *a,**k:pytest.fail('duplicate data must be rejected before execution'))
    with pytest.raises(training.TrainingEvidenceUnavailable,match='independent_cases_required'):
        prepare(tmp_path,snapshot,root,[('same','same'),('same','same')],config={'enabled':True},label='duplicate',
            case_inputs=[files,list(reversed(files))])


@pytest.mark.parametrize('change',['mapping','revoked','hidden_output'])
def test_published_method_cannot_change_arguments_or_hide_live_intermediate_outputs(tmp_path,observed,change):
    current,config=published_selection(tmp_path,observed);root=observed[1]
    selection=config['selection'];proposal={'format':'capability_compose_proposal_v1','owner':current['owner'],
        'contract':copy.deepcopy(root['contract']),**copy.deepcopy(root['implementation'])}
    proposal.pop('kind')
    if change=='mapping':
        row=json.loads(Path(selection['candidate']['path']).read_text())
        binding=next(item for item in row['provenance']['source_input_bindings'] if item['step_index']==1)
        binding['argument_path']=['value','after',binding['argument_path'][-1]]
        selection['candidate']=put(tmp_path/'changed-candidate.json',row)
    elif change=='revoked':
        caps=[{**cap,'certification':'candidate','lifecycle':'build_only'} if capability_ref(cap)==selection['root'] else cap
              for cap in current['capabilities']]
        current=create_capability_snapshot(current['owner'],current['roots'],caps)
    else:
        proposal['contract']['output_schema']={}
        proposal['output']={'kind':'step','step_id':'after','path':[]}
    with pytest.raises((ValueError,KeyError)):
        training._learned_prefix(proposal,current,selection)
