"""Read-only construction evidence views; original journals remain authoritative."""
from decimal import Decimal, InvalidOperation, localcontext
import json
from pathlib import Path

from .capability_contract import capability_digest
from .capability_feedback import file_ref
from .capability_improvement import evidence, save


def amount(value):
    if value is None:return None
    if isinstance(value,bool):raise ValueError('construction_cost_invalid')
    try:result=Decimal(str(value))
    except InvalidOperation as error:raise ValueError('construction_cost_invalid') from error
    if not result.is_finite() or result<0:raise ValueError('construction_cost_invalid')
    return result


def capture(job, attempt, snapshot, candidate=None, outcome=None, *, output=None):
    """Index a completed host attempt without rewriting its result or expenses."""
    attempt=Path(attempt)
    refs={name:file_ref(attempt/name) for name in ('result.json','requests.jsonl','strategy.json',
        'candidate.json','acquisition.json','effective.json','learning-provenance.json','evolution.json') if (attempt/name).is_file()}
    result=json.loads(evidence(refs['result.json']))
    if result.get('construction_snapshot_sha256',snapshot['digest'])!=snapshot['digest']:
        raise ValueError('construction_history_snapshot_changed')
    row={'format':'capability_construction_evidence_v1','goal_id':job['id'],'task':job['task'],
         'snapshot_sha256':snapshot['digest'],'sources':refs,
         'verification':outcome if candidate is not None else None,
         'model_feedback_allowed':not (outcome and outcome.get('committed') and outcome.get('status')!='published')}
    if outcome and outcome.get('evidence_ref'):evidence(outcome['evidence_ref'])
    path=Path(output) if output is not None else attempt/'construction-evidence.json';save(path,row)
    return file_ref(path)


def _request_keys(result, refs):
    """A result total needs matching booked ownership and settled observations."""
    if 'requests.jsonl' not in refs:
        return [], result.get('model_called') is False and result.get('provider_requests')==0
    raw=evidence(refs['requests.jsonl']).decode('utf-8')
    if not raw.endswith('\n'):raise ValueError('construction_request_journal_incomplete')
    booked={};settled={}
    for row in map(json.loads,raw.splitlines()):
        key=(str(Path(row['ledger_ref']).resolve()),row['request_id'])
        if row['phase']=='booked':
            if key in booked:raise ValueError('construction_duplicate_request_booking')
            booked[key]=row
        elif row['phase']=='settled':
            if key not in booked or key in settled:raise ValueError('construction_request_settlement_invalid')
            settled[key]=row
    if len(result.get('request_ids',[]))!=len(set(result.get('request_ids',[]))) or set(result.get('request_ids',[]))!={k[1] for k in booked} or result.get('provider_requests')!=len(booked):
        raise ValueError('construction_request_inventory_changed')
    if any(key[0]!=str(Path(result.get('ledger_ref','')).resolve()) for key in booked):
        raise ValueError('construction_request_ledger_changed')
    known=all(key in settled and settled[key].get('observed_peak_usd') is not None for key in booked)
    return list(booked),known


def build_history(records, task):
    """Rebuild all attempts, keeping missing/shared/non-model expenses explicit."""
    evidence(task);rows=[];seen=set();requests=set();total=Decimal(0);known=True;inventory_known=True;first=None
    with localcontext() as context:
        context.prec=1024
        for reference in records:
            identity=(str(Path(reference['path']).resolve()),reference['sha256'])
            if identity in seen:continue
            seen.add(identity);record=json.loads(evidence(reference))
            if record.get('format')!='capability_construction_evidence_v1' or record['task']['sha256']!=task['sha256']:
                raise ValueError('construction_history_task_changed')
            evidence(record['task']);refs=record['sources']
            sources={name:evidence(ref) for name,ref in refs.items()}
            result=json.loads(sources['result.json']);keys,observed=_request_keys(result,refs)
            if requests.intersection(keys):raise ValueError('construction_request_owner_changed')
            requests.update(keys)
            inventory_known=inventory_known and ('requests.jsonl' in refs or
                result.get('provider_requests')==0 and result.get('request_ids')==[])
            cost=amount(result.get('observed_model_usd_decimal',result.get('observed_model_usd')))
            if not observed:cost=None
            if observed and not keys and result.get('provider_requests')==0:cost=Decimal(0)
            known=known and cost is not None
            if cost is not None:total+=cost
            acquisition=json.loads(sources['acquisition.json']) if 'acquisition.json' in sources else None
            verification=record['verification']
            if verification and verification.get('evidence_ref'):evidence(verification['evidence_ref'])
            stage_costs={}
            for stage, value in (('acquisition',acquisition),('verification',verification)):
                if value is None:continue
                observed_cost=amount(value.get('observed_model_usd_decimal',value.get('observed_model_usd')))
                if value.get('model_requests')==0:observed_cost=Decimal(0)
                stage_costs[stage]=None if observed_cost is None else str(observed_cost)
            diagnostic=(acquisition or {}).get('diagnostics') or result.get('diagnostics') or {}
            failed_checks=[c for c in (verification or {}).get('feedback',{}).get('checks',[]) if c.get('status')!='passed']
            row={'evidence':reference,'result_ref':refs['result.json'],'status':result.get('status'),
                'snapshot_sha256':record['snapshot_sha256'],'error':(acquisition or {}).get('error') or
                    (verification or {}).get('error') or result.get('error'),
                'diagnostics':diagnostic,'failed_checks':failed_checks,
                'construction_gap':result.get('construction_gap'),'host_encoding':result.get('host_encoding'),
                'failure_cause':'unknown','model_explanation_is_hypothesis':True,
                'construction_model_usd_decimal':None if cost is None else str(cost),
                'request_keys':[{'ledger_ref':key[0],'request_id':key[1]} for key in keys],
                'other_stage_model_usd_decimal':stage_costs,
                'declared_strategy':json.loads(sources['strategy.json']) if 'strategy.json' in sources else None,
                'compiled_dependencies':json.loads(sources['candidate.json'])['capability']['dependencies'] if 'candidate.json' in sources else None,
                'verification':verification,'actual_dependencies':None}
            effective = json.loads(sources['effective.json']) if 'effective.json' in sources else {}
            if effective.get('inherited_strategy') is not None:
                row['inherited_strategy'] = effective['inherited_strategy']
                row['strategy_observation'] = result.get('strategy_observation')
            rows.append(row)
            if first is None and (verification or {}).get('status')=='published' and verification.get('evidence_ref'):
                first={'attempt_index':len(rows)-1,'construction_model_usd_decimal':str(total) if known else None}
    return {'format':'capability_construction_history_v1','task':task,'attempts':rows,
        'construction_model_usd_decimal':str(total) if known else None,
        'known_construction_model_usd_decimal':str(total),'physical_requests':len(requests) if inventory_known else None,
        'known_physical_requests':len(requests),
        'first_quality_success':first,'shared_discovery_model_usd_decimal':None,
        'all_stages_model_usd_decimal':None,'non_model_costs':None,
        'cost_scope':'construction_requests_only; shared discovery and other stages are not silently zero',
        'creation_efficiency':None,'strategy_improvement':None}


def feedback_library(library, history, *, trigger, budget, reconsider=False):
    import copy
    value=copy.deepcopy(library)
    value.setdefault('source_catalog',{})['construction_feedback']={
        'format':'capability_construction_feedback_v1','history':history,
        'snapshot_sha256':library['snapshot']['digest'],'trigger':trigger,
        'budget':budget,'reconsider':reconsider,
        'authority':'Evidence and model strategies grant no permission or quality certificate'}
    return value


def model_context(catalog, task, snapshot):
    source=catalog.get('source_catalog',catalog)
    value=source.get('construction_feedback')
    if value is None:return None
    if value.get('format')!='capability_construction_feedback_v1' or value['snapshot_sha256']!=snapshot['digest']:
        raise ValueError('construction_feedback_snapshot_changed')
    context=dict(value);history=json.loads(evidence(value['history']))
    if history['format']!='capability_construction_history_v1' or json.loads(evidence(history['task']))!=task:
        raise ValueError('construction_feedback_task_changed')
    # Rebuild rather than trusting an edited derivative view.
    if any(not json.loads(evidence(row['evidence'])).get('model_feedback_allowed',False) for row in history['attempts']):
        raise ValueError('construction_history_requires_review')
    rebuilt=build_history([row['evidence'] for row in history['attempts']],history['task'])
    if capability_digest(rebuilt)!=capability_digest(history):raise ValueError('construction_history_view_changed')
    from .capability_authoring import aliases
    table={capability_digest(ref):alias for alias,ref in aliases(snapshot).items()}
    for row in history['attempts']:
        declaration=row.get('declared_strategy') or {}
        row['expected_dependencies_current_aliases']=[table.get(capability_digest(ref))
            for ref in declaration.get('expected_dependencies',[])]
    context['history']=history
    context['historical_alias_scope']='Old uses aliases belong to each historical snapshot; use current aliases shown separately.'
    from .geneloop_privacy import learning_view
    return learning_view(context)


def unwrap_strategy(draft, output, snapshot, enabled):
    if not isinstance(draft,dict) or 'strategy' not in draft:return draft
    if not enabled or set(draft)!={'strategy','proposal'}:raise ValueError('proposal_strategy_shape_invalid')
    strategy=draft['strategy']
    if (not isinstance(strategy,dict) or set(strategy)!={'approach','reason','uses'}
            or any(not isinstance(strategy[k],str) or not strategy[k].strip() for k in ('approach','reason'))
            or not isinstance(strategy['uses'],list)):
        raise ValueError('proposal_strategy_shape_invalid')
    from .capability_authoring import aliases
    table=aliases(snapshot)
    if any(not isinstance(alias,str) or alias not in table for alias in strategy['uses']):
        raise ValueError('proposal_strategy_reference_not_visible')
    save(Path(output)/'strategy.json',{**strategy,'expected_dependencies':[table[alias] for alias in strategy['uses']],
        'actual_dependencies':None,'claim_scope':'model declaration, not observed strategy improvement'})
    return draft['proposal']


def inherited_strategy_context(catalog, snapshot):
    """Private host identity. The proposal boundary sanitizes its model copy."""
    config = catalog.get('source_catalog', catalog).get('inherited_strategy')
    if config is None:
        return None
    if not isinstance(config, dict) or type(config.get('enabled', False)) is not bool:
        raise ValueError('construction_inherited_strategy_config_invalid')
    if not config.get('enabled', False):
        return None
    if set(config) != {'enabled', 'selection', 'scope', 'feedback_directory'}:
        raise ValueError('construction_inherited_strategy_config_invalid')
    from .capability_feedback import CapabilityFeedback
    from .capability_strategy import strategy_context
    feedback = CapabilityFeedback(config['feedback_directory'], snapshot['owner'])
    context = strategy_context(config['selection'], snapshot, target='construction',
                               scope=config['scope'], feedback=feedback)
    from .capability_authoring import aliases
    context['capability_aliases'] = [alias for alias, ref in aliases(snapshot).items()
                                     if ref in context['capability_refs']]
    if len(json.dumps(context, ensure_ascii=False, allow_nan=False).encode('utf-8')) > 12000:
        raise ValueError('construction_inherited_strategy_context_too_large')
    return context
