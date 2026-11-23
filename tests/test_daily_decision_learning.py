"""Diagnostic lifecycle tests; real-model admission remains an integration check."""
import os
from pathlib import Path
from types import SimpleNamespace
import pytest
from src.adapters import daily_decision_learning as daily,continuous_rsi as rsi
from src.motif_core.reuse.experience_registry import digest,durable,read,sha


def config(root):
 return {'adapter':'management_v3','provider_mode':'real','mode':'learn','role':'ordinary',
  'state_root':str(root),'config_file':str(root/'config.json'),'auto_worker':True,'allow_material_copy':True,
  'series_cap_usd':None,'learning_cap_usd':None,'limits':{'budget_usd':None}}


def test_default_daily_mode_and_mock_observe_boundaries(tmp_path,monkeypatch):
 cfg=config(tmp_path)
 monkeypatch.delenv('SSS_FILE_PROVIDER_CONFIG',raising=False)
 assert not daily.enabled(cfg)
 monkeypatch.setenv('SSS_FILE_PROVIDER_CONFIG','private-provider-file')
 assert daily.enabled(cfg) is (os.name == 'posix')
 assert not daily.enabled({**cfg,'provider_mode':'mock'})
 assert not daily.enabled({**cfg,'mode':'observe'})
 assert not daily.enabled({**cfg,'adapter':'file_operations_v2'})


def test_frozen_plugin_uses_same_owner_account_catalogue_and_candidate(tmp_path,monkeypatch):
 cfg=config(tmp_path/'state');out=tmp_path/'run';out.mkdir()
 monkeypatch.setattr(rsi,'ROOT',tmp_path);monkeypatch.setattr(rsi,'PRIVATE_HOME',tmp_path/'account')
 monkeypatch.setattr(daily,'runtime_sources',lambda:{'runtime':'frozen'})
 monkeypatch.setenv('SSS_FILE_PROVIDER_CONFIG','private-provider-file')
 catalog=Path(cfg['state_root'])/'experience/versions/1.json';durable(catalog,{'jobs':[]})
 durable(Path(cfg['state_root'])/'experience/current.json',{'file':'versions/1.json'})
 p=daily.plugin(cfg,{'owner':'account-owner'},out,task_budget_usd=None)
 assert p['config']['catalog_sha256']==sha(catalog)
 assert p['config']['mode']=='execute' and p['config']['provider']=='jev'
 meter=read(p['config']['meter_context']);assert meter['owner']=='account-owner'
 assert meter['state_root']==cfg['state_root']
 assert 'credential'not in str(p)


@pytest.mark.parametrize(('account_budget', 'task_budget'), [(1, None), (None, 1)])
def test_finite_grant_remains_capture_only(tmp_path,monkeypatch,account_budget,task_budget):
 cfg=config(tmp_path/'state');cfg['limits']['budget_usd']=account_budget
 monkeypatch.setattr(rsi,'ROOT',tmp_path);monkeypatch.setattr(rsi,'PRIVATE_HOME',tmp_path/'account')
 monkeypatch.setattr(daily,'runtime_sources',lambda:{})
 monkeypatch.setenv('SSS_FILE_PROVIDER_CONFIG','private-provider-file')
 out=tmp_path/'run';out.mkdir();p=daily.plugin(cfg,{'owner':'owner'},out,task_budget_usd=task_budget)
 assert p['config']['mode']=='capture'
 assert cfg['limits']['budget_usd']==account_budget


def test_learning_excludes_holdouts_failed_and_stale_sources(tmp_path,monkeypatch):
 cfg=config(tmp_path);monkeypatch.setattr(rsi,'source_map',lambda:{})
 monkeypatch.setattr(daily,'runtime_sources',lambda:{'runtime':'current'})
 def record(name,**changes):
  origin=tmp_path/name;origin.mkdir();durable(origin/'task.json',{'learning_eligible':True})
  durable(origin/'enrollment.json',{'arguments':{'budget_usd':1 if name=='finite' else None}})
  out=origin/'out';(out/'decision-captures').mkdir(parents=True)
  durable(out/'rsi.patch.yml',[{'insert':[{'id':'geneloop-learned-decisions','config':{'runtime_sources':{'runtime':'old'if changes.get('source_sha256')=='old'else'current'}}}]}])
  return {'session_id':name,'origin':str(origin),'run_dir':str(out),'role':'ordinary','provider_mode':'real',
   'accepted':True,'accounting_complete':True,'lifecycle_verified':True,'source_sha256':rsi.digest({}),**changes}
 rows=[record('good'),record('cert',role='native_certification'),record('failed',accepted=False),record('stale',source_sha256='old'),record('finite'),record('holdout')]
 durable(Path(rows[-1]['origin'])/'task.json',{'learning_eligible':False})
 monkeypatch.setattr(rsi,'records',lambda root:rows)
 assert [r['session_id']for r in daily.eligible_records(cfg)]==['good']


@pytest.mark.skipif(os.name != 'posix', reason='Private paid decision execution is a POSIX feature')
def test_candidate_waits_for_two_independent_tasks_and_deduplicates(tmp_path,monkeypatch):
 cfg=config(tmp_path);monkeypatch.setenv('SSS_FILE_PROVIDER_CONFIG','private-provider-file')
 monkeypatch.setattr(rsi,'load_config',lambda path:cfg);monkeypatch.setattr(rsi,'source_map',lambda:{})
 monkeypatch.setattr(rsi,'state_event',lambda *a:None);monkeypatch.setattr(daily,'runtime_sources',lambda:{})
 values=[]
 for n in ['teacher-1','teacher-2','new-1','same-body','new-2']:
  origin=tmp_path/n;origin.mkdir();durable(origin/'task.json',{'initial_tree':{'workspace':{'files':{'input.txt':'teacher-body'if n.startswith('teacher')or n=='same-body'else n}}}})
  values.append({'session_id':n,'origin':str(origin)})
 available=values[:2];monkeypatch.setattr(daily,'eligible_records',lambda cfg:list(available))
 monkeypatch.setattr(daily,'opportunities',lambda cfg,rows:{'opportunities':[{'session_id':r['session_id'],'context':{}}for r in rows]})
 payload=tmp_path/'payload.json';durable(payload,{'candidate':{}})
 def generation(cfg,job,bundle):return {'status':'awaiting_independent_tasks','payload_file':str(payload),
  'guard_file':'guard','training_sessions':['teacher-1','teacher-2'],'training_hashes':['teacher-body'],
  'runtime_sources':{},'base_source_map':{},'certifications':[],'attempted_certification_sessions':[]}
 monkeypatch.setattr(daily,'generation',generation)
 monkeypatch.setattr(daily,'valid_training_roots',lambda *args:True)
 import src.adapters.learned_decision_certificate as certificate
 import src.adapters.empirical_decision_certificate as admission
 monkeypatch.setattr(certificate,'replay',lambda *a,**k:{'request':{'current':True}})
 tested=[]
 def certify(cfg,job,record,state):
  tested.append(record['session_id']);return {'status':'passed','result':record['session_id'],'local_review':'review','whole_reviews':['whole']}
 monkeypatch.setattr(daily,'certify',certify)
 activated=[];monkeypatch.setattr(admission,'publish_empirical',lambda *a,**k:activated.append(a)or{'status':'active'})
 assert daily.drain('config')['status']=='awaiting_independent_tasks'
 assert tested==[]
 available.extend(values[2:4]);daily.drain('config');daily.drain('config')
 assert tested==['new-1'] and not activated
 available.append(values[-1]);assert daily.drain('config')['status']=='active'
 assert tested==['new-1','new-2'] and len(activated)==1
 daily.drain('config');assert len(activated)==1


@pytest.mark.skipif(os.name != 'posix', reason='Private paid decision execution is a POSIX feature')
def test_active_worker_catches_a_new_seal_without_another_user_message(tmp_path,monkeypatch):
 monkeypatch.setenv('SSS_FILE_PROVIDER_CONFIG','private-provider-file')
 monkeypatch.setattr(rsi,'load_config',lambda path:config(tmp_path))
 rows=[{'session_id':'first'}];monkeypatch.setattr(daily,'eligible_records',lambda cfg:list(rows))
 calls=[]
 def once(path):
  calls.append(path)
  if len(calls)==1:rows.append({'session_id':'late-seal'})
  return {'status':'caught-up'}
 monkeypatch.setattr(daily,'_drain_once',once)
 assert daily.drain('config')['status']=='caught-up'and len(calls)==2


def test_daily_discovery_exposes_predecision_evidence_without_treating_outputs_as_inputs(tmp_path,monkeypatch):
 from src.adapters import learned_decision_learning as learning
 source={'snapshot_id':'s','session_id':'one','source_mode':'harness_plus_motif',
  'native_call':{'tool':'mcp__file_management__preview_actions','arguments':{'answer':'later-output'}},
  'source_visible_text':'later answer, not available before deciding',
  'task_total_requests':3,'task_acceptance_repairs':0,
  'context':{'goal':'interpret current evidence','receipts':{'read':{'text':'current unlabelled text'}},'history':[],'last_tool':'read'}}
 file=tmp_path/'sources.json';durable(file,{'opportunities':[source]});observed=[]
 def model(*args,**kwargs):
  observed.append((args[2],args[3]));return {'status':'completed','answer':{'selected_snapshot_ids':[],'reason':'no eligible pair'}}
 monkeypatch.setattr(learning,'model_json',model)
 outcome=learning.discover_indexed('config',file,tmp_path/'job',selection_only=True,daily_programs=True)
 system,data=observed[0];item=data['complete_request_index'][0]
 assert item['predecision_context']==source['context']
 assert item['observed_model_decision_output']['tool_call']==source['native_call']
 assert 'native_call'not in item and 'source_visible_text'not in item
 assert 'Semantic answers MUST be recomputed' in system
 assert outcome['answer']['reason']=='no eligible pair'


def test_empty_provider_call_ids_do_not_hide_valid_receipts_but_real_duplicates_still_fail():
 from src.adapters.continuous_motif_learning import observations
 empty={'type':'tool/call','seq':1,'data':{'callId':'','name':'','arguments':'{}'}}
 named={'type':'tool/call','seq':3,'data':{'callId':'actual','name':'read','arguments':'{}'}}
 result={'type':'tool/result','seq':4,'data':{'message':{'content':[{'type':'tool-result','toolCallId':'actual','content':[{'type':'text','text':'{"current":true}'}]}]}}}
 rows=observations([empty,{**empty,'seq':2},named,result])
 assert len(rows)==1 and rows[0]['call_id']=='actual' and rows[0]['out']=={'current':True}
 with pytest.raises(ValueError,match='duplicate call identity'):observations([named,{**named,'seq':5},result])


def test_program_identity_ignores_descriptions_but_not_execution_or_schema():
 p={'candidate':{'guard':['lit',True],'request':['lit',{}],'bind':['lit',{}],'description':'old'},
  'threshold':.9,'tool_schema_hashes':{'tool':'current'},'runtime_sources':{'runtime':'current'}}
 q={**p,'candidate':{**p['candidate'],'description':'new','training_witnesses':['new task']}}
 assert daily.executable_digest(p)==daily.executable_digest(q)
 q['candidate']['request']=['lit',{'different':True}]
 assert daily.executable_digest(p)!=daily.executable_digest(q)
 assert daily.executable_digest(p)!=daily.executable_digest({**p,'threshold':.8})


def test_training_root_must_match_two_real_sessions_and_declared_schema(tmp_path,monkeypatch):
 from src.adapters import learned_decision_certificate as certificate
 sources={'opportunities':[{'snapshot_id':str(i),'session_id':str(i),
  'native_call':{'tool':'native-root'},'context':{}}for i in range(2)]}
 source_file=tmp_path/'sources.json';durable(source_file,sources)
 payload={'candidate':{'training_witnesses':[{'snapshot_id':str(i),'values':{}}for i in range(2)]},
  'tool_schema_hashes':{'native-root':'schema'}}
 root=['different-root']
 monkeypatch.setattr(certificate,'replay',lambda *a,**k:{'binding':{'tool':root[0]}})
 assert not daily.valid_training_roots(payload,source_file)
 root[0]='native-root'
 assert daily.valid_training_roots(payload,source_file)
 assert not daily.valid_training_roots({**payload,'tool_schema_hashes':{}},source_file)
 sources['opportunities'][1]['session_id']='0';durable(source_file,sources)
 assert not daily.valid_training_roots(payload,source_file)


def test_background_compatibility_requires_identical_online_hooks_constants_and_imports():
 old='import json\nRUNTIME=["a"]\ndef enabled(x):return True\ndef plugin(x):return x\ndef runtime_sources():return RUNTIME\ndef learner():return 1\n'
 assert daily.same_online_hooks(old,old.replace('return 1','return 2'))
 assert not daily.same_online_hooks(old,old.replace('def plugin(x):return x','def plugin(x):return None'))
 assert not daily.same_online_hooks(old,old.replace('RUNTIME=["a"]','RUNTIME=[]'))
 assert not daily.same_online_hooks(old,old.replace('import json','import os'))


def test_offline_compatibility_keeps_old_quality_evidence_and_refuses_runtime_drift(tmp_path,monkeypatch):
 from src.adapters import experience_library
 root=tmp_path/'state';root.mkdir();cfg=config(root)
 name='src/adapters/daily_decision_learning.py';source=tmp_path/name;source.parent.mkdir(parents=True)
 before='import json\nRUNTIME=[]\ndef enabled(x):return True\ndef plugin(x):return x\ndef runtime_sources():return RUNTIME\ndef learner():return 1\n'
 source.write_text(before.replace('return 1','return 2'));runtime=tmp_path/'runtime.ts';runtime.write_text('unchanged')
 old_source=tmp_path/'original/frozen-source'/name;old_source.parent.mkdir(parents=True);old_source.write_text(before)
 record=tmp_path/'record.json';durable(record,{'origin':str(tmp_path/'original')})
 payload=root/'old-payload.json';durable(payload,{'owner':'one','candidate':{'guard':[],'request':[],'bind':[]},'threshold':.9,'tool_schema_hashes':{},'runtime_sources':{'runtime.ts':sha(runtime)}})
 cert=root/'old-certificate.json';durable(cert,{'status':'certified','reviews':[{'record_file':str(record)}],
  'payload_sha256':sha(payload),'runtime_sources':{name:sha(old_source),'runtime.ts':sha(runtime)},'base_source_map':{name:sha(old_source)}})
 activation=root/'experience/jobs/original/activation.json';a={'kind':'learned_decision_recipe','owner':'one','payload_file':str(payload),
  'payload_sha256':sha(payload),'certificate_file':str(cert),'certificate_sha256':sha(cert)};durable(activation,a)
 old_certificate_bytes=cert.read_bytes();old_activation_bytes=activation.read_bytes()
 monkeypatch.setattr(rsi,'ROOT',tmp_path);monkeypatch.setattr(rsi,'source_map',lambda:{name:sha(source),'runtime.ts':sha(runtime)})
 monkeypatch.setattr(experience_library,'synchronize',lambda cfg:None)
 assert len(daily.refresh_offline_compatible(cfg))==1
 assert cert.read_bytes()==old_certificate_bytes and activation.read_bytes()==old_activation_bytes
 wrappers=[p for p in(root/'experience/jobs').glob('*/activation.json')if p!=activation]
 proof=read(read(wrappers[0])['certificate_file'])
 assert proof['host_compatibility']['new_independent_certification']is False
 assert proof['reviews']==read(cert)['reviews']
 source.write_text(before.replace('return 1','return 3'))
 assert len(daily.refresh_offline_compatible(cfg))==1
 compatible=[]
 for p in(root/'experience/jobs').glob('*/activation.json'):
  proof=read(read(p)['certificate_file'])
  if all(sha(tmp_path/n)==h for n,h in proof['runtime_sources'].items()):compatible.append(p)
 assert len(compatible)==1
 runtime.write_text('changed actual runtime')
 assert daily.refresh_offline_compatible(cfg)==[]


def test_reviewed_source_relocation_preserves_frozen_catalogue_and_certification(tmp_path, monkeypatch):
    from src.adapters import experience_library

    root = tmp_path / '.local/state'
    root.mkdir(parents=True)
    cfg = config(root)
    name = 'src/adapters/daily_decision_learning.py'
    retired = 'src/adapters/decision_trial_judge_v5.py'
    runtime_file = tmp_path / 'runtime.ts'
    current_file = tmp_path / name
    current_file.parent.mkdir(parents=True)
    current_file.write_text('current daily host')
    runtime_file.write_text('same frozen decision runtime')
    runtime = {'runtime.ts': sha(runtime_file)}
    before = {name: 'frozen daily host', retired: 'frozen judge'}
    after = {name: sha(current_file)}
    monkeypatch.setattr(rsi, 'ROOT', tmp_path)
    monkeypatch.setattr(rsi, 'LEARNER', list(after))
    monkeypatch.setattr(rsi, 'source_map', lambda: after)
    reviewed = tmp_path / 'config/file-management-runtime-compatibility.json'
    durable(reviewed, {'schema_version': 1, 'enrollment_source_relocations': [
        {'before_sha256': digest(before), 'after_sha256': digest(after)}]})
    payload = root / 'old-payload.json'
    cert = root / 'old-certificate.json'
    durable(payload, {'owner': 'one', 'candidate': {'guard': [], 'request': [], 'bind': []},
                      'threshold': .9, 'tool_schema_hashes': {}, 'runtime_sources': runtime})
    activation = root / 'experience/jobs/original/activation.json'
    original_proof = {'status': 'certified', 'owner': 'one', 'reviews': [{'score': 10}],
                      'payload_sha256': sha(payload), 'runtime_sources': {**before, **runtime},
                      'base_source_map': before}

    def store_original_proof(proof):
        durable(cert, proof)
        durable(activation, {'kind': 'learned_decision_recipe', 'owner': 'one', 'payload_file': str(payload),
                             'payload_sha256': sha(payload), 'certificate_file': str(cert),
                             'certificate_sha256': sha(cert)})

    store_original_proof({**original_proof, 'runtime_sources': {**before, **runtime, 'unreviewed.py': 'extra'}})
    assert daily.refresh_offline_compatible(cfg) == []
    store_original_proof(original_proof)
    original_bytes = (activation.read_bytes(), cert.read_bytes())
    catalogue = root / 'experience/catalogues/original.json'
    row = {'job': 'experience/jobs/original', 'state': 'active'}
    durable(catalogue, {'jobs': [row], 'evidence': ['frozen']})
    durable(root / 'experience/current.json', {'file': str(catalogue.relative_to(root / 'experience'))})

    def synchronize(_):
        new_job, = [file for file in (root / 'experience/jobs').iterdir() if file.name != 'original']
        current = root / 'experience/catalogues/current.json'
        durable(current, {'jobs': [row, {'job': str(new_job.relative_to(root)), 'state': 'active'}]})
        durable(root / 'experience/current.json', {'file': str(current.relative_to(root / 'experience'))})

    monkeypatch.setattr(experience_library, 'synchronize', synchronize)
    frozen = {'state_root': str(root), 'mode': 'execute', 'catalog_file': str(catalogue),
              'catalog_sha256': sha(catalogue), 'runtime_sources': runtime}
    assert daily.compatible_decision_config(frozen, tmp_path / '.local/unrelated', owner='two') is frozen
    current = daily.compatible_decision_config(frozen, tmp_path / '.local/current', owner='one', refresh_cfg=cfg)
    new_row, = read(current['catalog_file'])['jobs']
    new_proof = read(read(root / new_row['job'] / 'activation.json')['certificate_file'])
    assert new_proof['base_source_map'] == after
    assert new_proof['runtime_sources'] == {**after, **runtime}
    assert new_proof['reviews'] == original_proof['reviews']
    assert new_proof['host_compatibility']['new_independent_certification'] is False
    assert (activation.read_bytes(), cert.read_bytes()) == original_bytes
    assert read(catalogue)['jobs'] == [row]
    assert current['runtime_sources'] == runtime

    resumed = daily.compatible_decision_config(frozen, tmp_path / '.local/attempt', owner='one')
    assert read(resumed['catalog_file']) == {'jobs': [], 'evidence': ['frozen']}
    assert resumed['runtime_sources'] == runtime
    runtime_file.write_text('changed actual runtime')
    assert daily.refresh_offline_compatible(cfg) == []
