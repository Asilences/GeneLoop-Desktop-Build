"""Freeze multiple final projects and budgets without models or candidate runs."""
import hashlib
import json

import pytest

from scenarios.paper_proofreading.frontier.prepare_D import (
    final_project_checks,finite_budget,freeze_research_budget,load_final_projects,
)


def manifest(tmp_path,project_id='dora',explicit_versions=True):
    folder=tmp_path/(project_id or 'legacy');folder.mkdir()
    rows=[]
    for version in range(3):
        path=folder/f'v{version}.zip';path.write_bytes(f'input-{version}'.encode())
        row={'file':path.name,'sha256':hashlib.sha256(path.read_bytes()).hexdigest()}
        if explicit_versions:row['version']=version
        rows.append(row)
    value={'versions':rows}
    if project_id is not None:value['id']=project_id
    path=folder/'manifest.json';path.write_text(json.dumps(value))
    return path,value


def test_multiple_final_projects_use_named_versions_and_distinct_checks(tmp_path):
    dora,d=manifest(tmp_path,'dora');bitfit,b=manifest(tmp_path,'bitfit')
    d['versions'].reverse();dora.write_text(json.dumps(d))
    projects=load_final_projects([dora,bitfit])
    assert [p['id'] for p in projects]==['dora','bitfit']
    assert final_project_checks(projects)==['dora_v0_v1','dora_v1_v2','bitfit_v0_v1','bitfit_v1_v2']
    assert projects[0]['versions']['0']['path']==str(dora.parent/'v0.zip')
    assert projects[1]['source_manifest']['sha256']==hashlib.sha256(bitfit.read_bytes()).hexdigest()


def test_legacy_single_manifest_preserves_mamba_and_order(tmp_path):
    path,_=manifest(tmp_path,None,False)
    projects=load_final_projects([path])
    assert projects[0]['id']=='mamba'
    assert list(projects[0]['versions'])==['0','1','2']
    assert final_project_checks(projects)==['mamba_v0_v1','mamba_v1_v2']
    with pytest.raises(ValueError,match='manifest_required'):load_final_projects([])


@pytest.mark.parametrize('bad_id',['../outside','bad/id','',123,'a'*65])
def test_final_project_ids_are_safe(tmp_path,bad_id):
    path,value=manifest(tmp_path)
    value['id']=bad_id;path.write_text(json.dumps(value))
    with pytest.raises(ValueError,match='project_id_invalid'):load_final_projects([path])


def test_duplicate_project_ids_are_rejected(tmp_path):
    path,_=manifest(tmp_path)
    with pytest.raises(ValueError,match='project_id_invalid'):load_final_projects([path,path])


@pytest.mark.parametrize('bad_version',[True,3,-1,'0',1])
def test_final_version_mapping_must_be_exact(tmp_path,bad_version):
    path,value=manifest(tmp_path)
    value['versions'][0]['version']=bad_version;path.write_text(json.dumps(value))
    with pytest.raises(ValueError,match='versions_invalid'):load_final_projects([path])


@pytest.mark.parametrize('name',['../outside.zip','/tmp/outside.zip','sub/../../outside.zip','sub\\outside.zip',''])
def test_final_source_cannot_escape_manifest_directory(tmp_path,name):
    path,value=manifest(tmp_path)
    value['versions'][0]['file']=name;path.write_text(json.dumps(value))
    with pytest.raises(ValueError,match='source_path_invalid'):load_final_projects([path])


def test_final_source_symlink_escape_and_hash_mutation_are_rejected(tmp_path):
    path,value=manifest(tmp_path)
    outside=tmp_path/'outside.zip';outside.write_bytes(b'outside')
    (path.parent/'link.zip').symlink_to(outside)
    value['versions'][0]['file']='link.zip';path.write_text(json.dumps(value))
    with pytest.raises(ValueError,match='source_path_invalid'):load_final_projects([path])
    value['versions'][0]['file']='v0.zip';path.write_text(json.dumps(value))
    (path.parent/'v0.zip').write_bytes(b'changed')
    with pytest.raises(ValueError,match='inputs_changed'):load_final_projects([path])


def test_research_budget_keeps_unknown_reserve_and_decimal_boundary(tmp_path):
    path=tmp_path/'journal.jsonl'
    rows=[{'event':'request_booked','request_id':1,'reserved_upper_usd':'0.80'},
          {'event':'request_settled','request_id':1,'observed_model_usd':'0.10'},
          {'event':'request_booked','request_id':2,'reserved_upper_usd':'0.20'},
          {'event':'request_settled','request_id':2,'observed_model_usd':None}]
    path.write_text(''.join(json.dumps(row)+'\n' for row in rows))
    result=freeze_research_budget('0.10','0.90',6,[path])
    assert result['prior_accounted_upper_usd']=='0.30'
    assert result['aggregate_planned_upper_usd']=='0.90'
    assert result['aggregate_model_estimate_limit_usd']=='0.90'
    with pytest.raises(ValueError,match='budget_exceeded'):freeze_research_budget('0.1000000001','0.90',6,[path])
    assert freeze_research_budget('0.80','6.00',6,[])['aggregate_planned_upper_usd']=='4.80'
    assert freeze_research_budget('2','12',6,[])['aggregate_planned_upper_usd']=='12'


@pytest.mark.parametrize('value',['NaN','Infinity','-1','bad'])
def test_research_limits_must_be_finite_nonnegative(value):
    with pytest.raises(ValueError,match='budget_invalid'):finite_budget(value)
    assert finite_budget('0')=='0'
