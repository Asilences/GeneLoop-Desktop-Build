"""Certify a current-goal shape relation against a reviewed pure validator.

This is a data-contract primitive, not arbitrary black-box cause discovery.
No historical lengths, report text or field positions become runtime rules.
"""
import copy
from src.motif_core.offline.compilation.script_motif_compiler import digest
from src.motif_core.trajectory.negative_outcome import negative_outcome

def shape_issues(expected,actual,path=''):
    if isinstance(expected,(int,float)) and not isinstance(expected,bool):
        raise ValueError('numeric_shape_not_portable')
    if type(expected) is not type(actual):
        return [{'pointer':path,'expected_type':type(expected).__name__,'actual_type':type(actual).__name__}]
    if isinstance(expected,list):
        if len(expected)!=len(actual):return [{'pointer':path,'expected_items':len(expected),'actual_items':len(actual)}]
        return [v for i,(a,b) in enumerate(zip(expected,actual)) for v in shape_issues(a,b,path+'/'+str(i))][:32]
    if isinstance(expected,dict):
        if set(expected)!=set(actual):return [{'pointer':path,'expected_keys':sorted(expected),'actual_keys':sorted(actual)}]
        return [v for k in expected for v in shape_issues(expected[k],actual[k],path+'/'+k.replace('~','~0').replace('/','~1'))][:32]
    return []

def project(value,path):
    for k in path.split('/')[1:]:
        k=k.replace('~1','/').replace('~0','~');value=value[int(k)] if isinstance(value,list) else value[k]
    return value

def replace(value,path,replacement):
    keys=[k.replace('~1','/').replace('~0','~') for k in path.split('/')[1:]]
    if not keys:return copy.deepcopy(replacement)
    parent=value
    for k in keys[:-1]:parent=parent[int(k)] if isinstance(parent,list) else parent[k]
    parent[int(keys[-1]) if isinstance(parent,list) else keys[-1]]=copy.deepcopy(replacement)
    return value

def certify_current_constraint(rule,observations,validator):
    failed_ids={(w['task_id'],w['call_id']) for w in rule['certification']['failures']}
    success_ids={(w['task_id'],w['call_id']) for w in rule['certification']['success_contrasts']}
    failures=[];successes=[];interventions=[]
    for row in observations:
        if row['tool']!=rule['tool']:continue
        key=(row['task_id'],row['call_id']);goal,args=row['goal'],row['arguments']
        actual=validator(goal,args);predicted=shape_issues(goal,args)
        if digest(actual)!=digest(predicted):raise ValueError('constraint_provider_disagreement')
        if key in success_ids and negative_outcome(row['result'])['status']=='success' and not actual:
            successes.append({k:row[k] for k in ['task_id','call_id','events_sha256']})
        if key not in failed_ids or not actual or digest(actual)!=digest(row['result'].get('scope_issues')):continue
        checks={i.get('check') for i in row['result'].get('argument_issues',[])}
        if rule['failure_code'] not in checks:continue
        repaired=copy.deepcopy(args)
        for issue in actual:repaired=replace(repaired,issue['pointer'],project(goal,issue['pointer']))
        if validator(goal,repaired) or shape_issues(goal,repaired):continue
        reintroduced=copy.deepcopy(goal)
        for issue in actual:reintroduced=replace(reintroduced,issue['pointer'],project(args,issue['pointer']))
        if not validator(goal,reintroduced) or not shape_issues(goal,reintroduced):continue
        unrelated=[]
        def strings(v,path=''):
            if isinstance(v,dict):
                for k,x in v.items():yield from strings(x,path+'/'+k.replace('~','~0').replace('/','~1'))
            elif isinstance(v,list):
                for i,x in enumerate(v):yield from strings(x,path+'/'+str(i))
            elif isinstance(v,str):yield path,v
        for path,value in strings(args):
            if any(path==i['pointer'] or path.startswith(i['pointer']+'/') for i in actual):continue
            changed=replace(copy.deepcopy(args),path,value+' diagnostic')
            if digest(validator(goal,changed))==digest(actual):unrelated.append(path)
            if len(unrelated)==2:break
        if len(unrelated)<2:continue
        failures.append({k:row[k] for k in ['task_id','call_id','events_sha256']})
        interventions.append({'failure_state_sha256':digest([goal,args]),'repair_state_sha256':digest([goal,repaired]),
            'reintroduction_state_sha256':digest([goal,reintroduced]),'unrelated_edit_paths':unrelated,
            'repair_passed':True,'reintroduction_failed':True})
    if len(failures)<2 or not successes:raise ValueError('current_constraint_witnesses_insufficient')
    return {'version':1,'kind':'current_scope_shape','scope_file':'review-recovery-scope.json','tool':rule['tool'],'failure_code':rule['failure_code'],
            'certification':{'scope':'reviewed_validator_and_real_scope_shape_not_semantic_quality',
                'failures':failures,'successes':successes,'interventions':interventions}}


def recertify_current_constraints(library, observations, validator, validator_ref, historical_sources):
    """Re-certify necessary conditions, never migrate historical tool authority.

    A changed tool implementation invalidates ordinary trace compilation. This
    explicit path retains only rules independently certified by the CURRENT
    reviewed pure validator. The online runtime must still observe that failure
    on the current tool, bind its evidence and deliver a warning before blocking.
    Historical successes are contrasts for this predicate, not certification of
    the new tool's execution, rendering or scientific quality.
    """
    name, function = validator_ref.split(':')
    if name not in library['implementation_locks'] or not function.isidentifier() or not historical_sources:
        raise ValueError('current_constraint_validator_and_history_required')
    result = copy.deepcopy(library)
    retained, dropped = [], []
    for rule in result['rules']:
        try:
            if rule.get('failure_source') != 'failed_checks':
                raise ValueError('current_constraint_failure_source_required')
            guard = certify_current_constraint(rule, observations, validator)
        except (ValueError, KeyError, TypeError) as error:
            dropped.append({'rule_id': rule['id'], 'failure_code': rule['failure_code'], 'reason': str(error)})
            continue
        guard.update(validator=validator_ref, validator_sha256=result['implementation_locks'][name])
        rule.update(argument_guard=guard, retry_policy='warn_then_current_constraint')
        rule['id'] = 'negative_' + digest({k: v for k, v in rule.items() if k != 'id'})[:16]
        retained.append(rule)
    if not retained:
        raise ValueError('no_current_constraints_recertified')
    result['rules'] = retained
    result['recertification'] = {
        'kind': 'current_constraint_recertification',
        'scope': 'current_predicate_and_bound_live_failure_not_historical_tool_execution',
        'validator': validator_ref, 'historical_sources': historical_sources, 'dropped_rules': dropped,
    }
    result['digest'] = digest({k: v for k, v in result.items() if k != 'digest'})
    return result
