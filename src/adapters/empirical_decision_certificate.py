"""Outcome-led local admission; old strict certificates remain immutable.

Training narration/order and synthetic complete-before-every-decision probes are
diagnostics. New task delivery and the actual substituted call decide admission.
"""
from pathlib import Path
from src.motif_core.reuse.experience_registry import read,sha,digest,durable,ExperienceRegistry
from .learned_decision_learning import generated_candidate
from .learned_decision_certificate import ROOT,FORMAT,REVIEW_SYSTEM,reviewed,execution_evidence

PROFILE='empirical-task-outcomes-v2'
LOCAL_SYSTEM=REVIEW_SYSTEM+'''
Judge this CURRENT bounded decision, not fidelity to the old training narration or incidental plan ordering.
A correctly labelled preview may be sufficient to classify a CSV or select a category. Do not require every byte of every file before every local decision unless the actual user goal explicitly requires that order, or the decision truly depends on unseen content. Full-reading obligations for the completed task are checked in the independent whole-task evidence.
Never accept a false claim that a preview is the complete document, a conclusion requiring unseen evidence, wrong binding, expanded permission, or a task-specific temporal violation. Ordinary Harness may complete further reading/reporting and repair unrelated task issues; record those costs without rejecting a correct local call simply because a repair occurred.'''


def check_empirical_guards(payload_file,guard_file):
    guard=read(guard_file)
    if guard.get('payload_sha256')!=sha(payload_file):raise ValueError('guard evidence belongs to another candidate')
    required={'readonly_goal','all_read_evidence_absent'}
    payload=read(payload_file)
    from .decision_source_equivalence import POLICY
    if payload.get('source_argument_equivalence')==POLICY:
        required|={'explicit_copy_order','lexicographic_copy_order','reverse_copy_order'}
    cases=guard.get('cases',[])
    for witness in read(payload_file)['candidate']['training_witnesses']:
        rows=[r for r in cases if r['snapshot_id']==witness['snapshot_id']]
        names={r['case']for r in rows if r.get('passed')}
        if not required<=names:raise ValueError('read/permission/explicit-order mismatch guard failed')
        roles={r['case']for r in rows if r['case'].startswith('category_role_') or r['case'].startswith('unfamiliar_')}
        if not roles<=names:raise ValueError('fixed category meanings must not silently change')
    return {'profile':PROFILE,'required_checks_passed':True,
            'advisory_failures':[r for r in cases if not r.get('passed')],
            'preview_is_not_complete_read':True,'whole_task_reading_still_required':True}


def publish_empirical(config_file,payload_file,result_files,local_review_files,whole_review_files,guard_file,*,source_diagnostics=(),allowed_providers=('jev','jev+deepseek','deterministic'),daily_file=False):
    from .continuous_rsi import load_config,source_map,state_event
    from .experience_library import synchronize
    from .file_management.decision_trial_judge import HETEROGENEOUS_PACKET_FORMAT, SOURCE_PATH, heterogeneous_packet
    cfg=load_config(config_file);state=Path(cfg['state_root']);value=read(payload_file)
    if not allowed_providers or not set(allowed_providers)<={'jev','jev+deepseek','deepseek','deterministic'}:raise ValueError('explicit known certification providers required')
    if value['candidate_sha256']!=digest(value['candidate']) or generated_candidate(value['model_generation_file'])!=value['candidate']:
        raise ValueError('actual generated program provenance required')
    if sha(value['model_generation_file'])!=value['model_generation_sha256'] or sha(value['model_response_file'])!=value['model_response_sha256']:
        raise ValueError('original model source changed')
    if any(sha(ROOT/n)!=s for n,s in value['runtime_sources'].items()):raise ValueError('execution dependency changed')
    guards=check_empirical_guards(payload_file,guard_file)
    if len(result_files)<2 or len(local_review_files)!=len(result_files) or len(whole_review_files)!=len(result_files):
        raise ValueError('two fresh independent executions and their reviews required')
    rows=[execution_evidence(payload_file,f,state,allow_task_repairs=True)for f in result_files]
    training_tasks=set();training_hashes=set()
    for source in value['training_sources']:
        if sha(source['record_file'])!=source['record_sha256'] or sha(source['capture_file'])!=source['capture_sha256']:
            raise ValueError('training provenance changed')
        rec=read(source['record_file']);spec=read(Path(rec['origin'])/'task.json')
        training_tasks.add(rec['task_fingerprint'])
        training_hashes.update(h for n,h in spec['initial_tree']['workspace']['files'].items()if not n.startswith('.'))
    if len({r['fingerprint']for r in rows})!=len(rows) or any(r['fingerprint']in training_tasks or set(r['input_hashes'])&training_hashes for r in rows):
        raise ValueError('independent material overlaps training')
    refs=[guard_file,*source_diagnostics]
    for row,local_file,whole_file in zip(rows,local_review_files,whole_review_files):
        if not row['local'] or any(e['provider']not in allowed_providers for e in row['local']):
            raise ValueError('actual successful certified-provider tool substitution required')
        data={'kind':'independent_actual_substitution','payload_sha256':sha(payload_file),
              'record_sha256':row['record_sha256'],'cases':[e['review_input']for e in row['local']]}
        if not reviewed(read(local_file)) or read(local_file)['input_sha256']!=digest({'system':LOCAL_SYSTEM,'data':data}):
            raise ValueError('actual local decision failed independent review')
        whole=read(whole_file)
        if whole.get('packet_format')!=HETEROGENEOUS_PACKET_FORMAT or not whole.get('passed') or whole['input_sha256']!=digest(heterogeneous_packet(Path(row['result_file']).parent)):
            raise ValueError('independent completed task quality failed')
        refs.extend([local_file,whole_file])
    cert={'format':FORMAT,'status':'certified','profile':PROFILE,'owner':value['owner'],
          'candidate_sha256':value['candidate_sha256'],'payload_sha256':sha(payload_file),
          'runtime_sources':{**source_map(),**value['runtime_sources']},'base_source_map':source_map(),
          'reviews':rows,'guard_assessment':guards,
          'independent_reviews':[{'file':str(f),'sha256':sha(f)}for f in refs],
          'certifier_sources':{str(Path(__file__).relative_to(ROOT)):sha(__file__),
              'src/adapters/learned_decision_certificate.py':sha(ROOT/'src/adapters/learned_decision_certificate.py'),
              SOURCE_PATH:sha(ROOT/SOURCE_PATH)},
          'training_equivalence_is_advisory':True,'task_repairs_counted_not_automatically_rejected':True,
          'per_recipe_mixed_branch_not_required':True,'new_recipe_mixed_execution_observed':any(e['provider']=='jev+deepseek'for r in rows for e in r['local']),
          'final_holdout_used':False,'quality_and_permission_required':True,'net_benefit_required':False,
          'default_frontend_enabled':bool(daily_file)}
    cert['execution_providers']=sorted({e['provider']for r in rows for e in r['local']})
    cert['allowed_certification_providers']=list(allowed_providers)
    job=state/'experience/jobs'/('learned-decision-'+sha(payload_file));job.mkdir(parents=True,exist_ok=True,mode=0o700)
    certificate=job/'certificate.json';durable(certificate,cert,exclusive=True)
    store=ExperienceRegistry(state/'experience');pf,ph=store.object(payload_file);cf,ch=store.object(certificate)
    activation={'status':'activated_for_daily_file' if daily_file else 'activated_for_opt_in_trial','kind':'learned_decision_recipe','profile':PROFILE,
                'owner':value['owner'],'payload_file':str(state/'experience'/pf),'payload_sha256':ph,
                'certificate_file':str(state/'experience'/cf),'certificate_sha256':ch,
                'same_original_pool':True,'default_frontend_enabled':bool(daily_file),'new_native_motif_entries':0}
    durable(job/'activation.json',activation,exclusive=True);state_event(state,'learned_decision_recipe_certified',activation);synchronize(cfg)
    return activation
