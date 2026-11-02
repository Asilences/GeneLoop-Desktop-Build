"""Compact model-facing Compose draft; deterministic encoding, never semantic repair.

Aliases are derived only from one validated frozen snapshot. Runtime IR and
certification are unchanged. Legacy full proposals remain strictly checked.
"""
from __future__ import annotations
import copy
import json
from .capability_contract import capability_digest, validate_capability_snapshot

FORMAT = 'capability_compose_draft_v1'


class AuthoringError(ValueError):
    def __init__(self, reason, path, expected, actual):
        super().__init__('proposal_'+reason)
        self.diagnostics = {'kind':'authoring','error':str(self),'issues':[
            {'path':list(path),'expected':expected,'actual':actual}]}


def _shape(value, keys, path):
    if not isinstance(value,dict) or set(value)!=set(keys):
        raise AuthoringError('draft_shape',path,{'keys':list(keys)},list(value) if isinstance(value,dict) else value)


def aliases(snapshot):
    snapshot=validate_capability_snapshot(snapshot)
    return {'c'+str(index+1):copy.deepcopy(ref) for index,ref in enumerate(snapshot['roots'])}


def compact_binding(binding):
    kind=binding['kind']
    if kind=='input':return {'$input':copy.deepcopy(binding['path'])}
    if kind=='step':return {'$step':[binding['step_id'],*binding['path']]}
    if kind=='literal':
        value=copy.deepcopy(binding['value'])
        return {'$literal':value} if isinstance(value,(dict,list)) else value
    if kind=='object':return {key:compact_binding(value) for key,value in binding['fields'].items()}
    if kind=='array':return [compact_binding(value) for value in binding['items']]
    raise ValueError('proposal_unknown_binding')


def compact_proposal(proposal, task, snapshot):
    """Diagnostic roundtrip of a valid full proposal, not an automatic fixer."""
    from .capability_builder import compile_proposal
    compile_proposal(proposal,snapshot,snapshot['owner'])
    if 'contract' in task and proposal['contract']!=task['contract']:
        raise AuthoringError('task_contract_changed',['contract'],task['contract'],proposal['contract'])
    reverse={ref['id']:name for name,ref in aliases(snapshot).items()}
    draft={'steps':[{'id':step['id'],'use':reverse[step['capability']['id']],
                    'args':compact_binding(step['arguments'])} for step in proposal['steps']],
           'output':compact_binding(proposal['output'])}
    if 'contract' not in task:draft['contract']=copy.deepcopy(proposal['contract'])
    return draft


def authoring_context(task, snapshot, catalog):
    table=aliases(snapshot)
    source=catalog.get('source_catalog',catalog) if isinstance(catalog,dict) else {}
    descriptions={}
    if isinstance(source,dict):
        seed=source.get('seed',{})
        rows=[*source.get('catalog',[]),
              *(seed.get('catalog',[]) if isinstance(seed,dict) else []),
              *source.get('admitted_materials',[])]
        for row in rows:
            if isinstance(row,dict) and isinstance(row.get('capability'),dict):
                descriptions[(row['capability'].get('id'),row['capability'].get('sha256'))]=row
    lookup={cap['id']:cap for cap in snapshot['capabilities']}
    capabilities=[]
    for name,ref in table.items():
        cap=lookup[ref['id']];description=descriptions.get((ref['id'],ref['sha256']),{})
        item={'alias':name,'contract':copy.deepcopy(cap['contract'])}
        for key in ('description','example_parameters'):
            if key in description:item[key]=copy.deepcopy(description[key])
        # Learned composition structure remains inspectable, using aliases only
        # where the referenced dependency is also a visible selectable root.
        item['kind']=cap['implementation']['kind']
        if item['kind']=='composition':
            reverse={r['id']:alias for alias,r in table.items()}
            implementation=cap['implementation']
            item['definition']={'steps':[{'id':step['id'],
                'use':reverse.get(step['capability']['id'],'non_selectable_dependency'),
                'args':compact_binding(step['arguments'])} for step in implementation['steps']],
                'output':compact_binding(implementation['output'])}
        capabilities.append(item)
    preferred=catalog.get('preferred_roots',[]) if isinstance(catalog,dict) else []
    order={ref['id']:i for i,ref in enumerate(preferred) if ref in table.values()}
    capabilities.sort(key=lambda item:order.get(table[item['alias']]['id'],len(order)))
    context={'authoring_format':FORMAT,'task':copy.deepcopy(task),'capabilities':capabilities,
             'contract_mode':'host_fixed' if 'contract' in task else 'model_designed'}
    continuation=source.get('material_continuation') if isinstance(source,dict) else None
    if continuation is not None:
        if continuation.get('format')!='capability_material_continuation_v1' or continuation.get('current_snapshot_sha256')!=snapshot['digest']:
            raise AuthoringError('material_continuation_changed',['material_continuation'],'current construction snapshot',continuation)
        from .capability_improvement import evidence
        reverse={ref['id']:name for name,ref in table.items()};records=[]
        for ref in continuation['acquisitions']:
            record=json.loads(evidence(ref))
            if record.get('format')!='capability_material_acquisition_v1':raise ValueError('proposal_material_acquisition_invalid')
            for source_ref in record['evidence']:evidence(source_ref)
            record['current_aliases']=[{'capability':r,'alias':reverse[r['id']]} for r in record['newly_visible'] if r in table.values()]
            records.append(record)
        context['material_continuation']={'scope':'Completed material acquisitions, not a same-snapshot repair. Prior aliases may have changed; use current aliases and contracts. All permitted implementations remain available; no choice is mandated.',
            'current_snapshot_sha256':snapshot['digest'],'acquisitions':records}
    return context


def expand_binding(value, path=(), depth=0):
    """Encode one compact binding without selecting a capability or a value."""
    path=list(path)
    if depth>48:raise AuthoringError('draft_too_deep',path,'depth <=48',depth)
    if isinstance(value,dict):
        operators=[k for k in value if k.startswith('$')]
        if operators:
            if len(value)!=1 or operators[0] not in ('$input','$step','$literal'):
                raise AuthoringError('draft_binding',path,'exactly one of $input/$step/$literal',value)
            operator=operators[0];operand=value[operator]
            if operator=='$literal':return {'kind':'literal','value':copy.deepcopy(operand)}
            if not isinstance(operand,list) or any(not isinstance(x,str) or x in ('__proto__','prototype','constructor') for x in operand):
                raise AuthoringError('draft_path',path+[operator],'array of safe property names',operand)
            if operator=='$input':return {'kind':'input','path':operand}
            if not operand:raise AuthoringError('draft_path',path+[operator],'step id followed by optional property names',operand)
            return {'kind':'step','step_id':operand[0],'path':operand[1:]}
        return {'kind':'object','fields':{key:expand_binding(child,path+[key],depth+1) for key,child in value.items()}}
    if isinstance(value,list):return {'kind':'array','items':[expand_binding(child,path+[i],depth+1) for i,child in enumerate(value)]}
    return {'kind':'literal','value':value}


def expand_draft(draft, task, snapshot):
    """Encode decisions into the existing IR, retaining model step order/choices."""
    capability_digest(draft)
    snapshot=validate_capability_snapshot(snapshot)
    if isinstance(draft,dict) and draft.get('format')=='capability_compose_proposal_v1':
        if 'contract' in task and draft.get('contract')!=task['contract']:
            raise AuthoringError('task_contract_changed',['contract'],task['contract'],draft.get('contract'))
        return copy.deepcopy(draft)  # compiler still verifies owner/refs/shape
    required=['steps','output']+([] if 'contract' in task else ['contract'])
    _shape(draft,required,[])
    table=aliases(snapshot)
    steps=draft['steps']
    if not isinstance(steps,list) or not 1<=len(steps)<=64:
        raise AuthoringError('draft_steps',['steps'],'array of 1..64 steps',steps)

    expanded=[]
    for index,step in enumerate(steps):
        path=['steps',index];_shape(step,['id','use','args'],path)
        name=step['use']
        if not isinstance(name,str) or name not in table:
            raise AuthoringError('reference_not_visible',path+['use'],list(table),name)
        expanded.append({'id':step['id'],'capability':table[name],
                         'arguments':expand_binding(step['args'],path+['args'])})
    return {'format':'capability_compose_proposal_v1','owner':snapshot['owner'],
            'contract':copy.deepcopy(task.get('contract',draft.get('contract'))),
            'steps':expanded,'output':expand_binding(draft['output'],['output'])}


def diagnose(error, proposal=None):
    if isinstance(error,json.JSONDecodeError):
        return {'kind':'json_syntax','line':error.lineno,'column':error.colno,'message':error.msg,
                'issues':[{'path':[],'expected':'one complete JSON object','actual':{'line':error.lineno,'column':error.colno}}]}
    if hasattr(error,'diagnostics'):return copy.deepcopy(error.diagnostics)
    # Older structural validators keep their error codes. Location is attached
    # by the validator where available, rather than guessed by a second checker.
    return {'kind':'compile','path_space':'compiled_proposal','error':str(error) if str(error).startswith(('capability_','proposal_')) else type(error).__name__,
            'issues':[{'path':list(getattr(error,'capability_path',())),
                       'expected':getattr(error,'capability_expected','valid capability proposal'),
                       'actual':getattr(error,'capability_actual',None)}],
            'passed_checks':getattr(error,'passed_checks',[])}
