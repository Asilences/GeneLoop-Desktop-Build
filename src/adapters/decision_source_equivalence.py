"""Read-only source replay proofs; never reorder a generated/executed plan.

The optional File rule permits only disjoint new workspace copies after an
unchanged mkdir prefix. Natural-language ordering must separately be admitted
by the independent source reviewer. All other operations remain ordered.
"""
from .learned_decision_learning import schema_default_arguments
from src.motif_core.reuse.experience_registry import digest

POLICY='explicit_schema_defaults_and_disjoint_workspace_copies_v2'


def source_argument_proof(binding,source,*,allow_disjoint_copies=False):
    tool=next(t for t in source['tools'] if t['name']==source['native_call']['tool'])
    if not binding or binding.get('tool')!=tool['name']:return None
    expected=schema_default_arguments(source['native_call']['arguments'],tool['parameters'])
    actual=schema_default_arguments(binding['arguments'],tool['parameters'])
    if expected==actual:return {'kind':'ordered_schema_defaults_v1','arguments_sha256':digest(actual)}
    if not allow_disjoint_copies or tool['name']!='mcp__file_management__preview_actions':return None
    if source.get('native_output',{}).get('status')!='validated_management_plan':return None
    if {k:v for k,v in actual.items() if k!='actions'}!={k:v for k,v in expected.items() if k!='actions'}:return None
    def partition(value):
        actions=value.get('actions')
        if not isinstance(actions,list):return None
        start=next((i for i,a in enumerate(actions) if a.get('op')!='mkdir'),len(actions))
        prefix,suffix=actions[:start],actions[start:]
        if not suffix or any(a.get('op')!='copy' for a in suffix):return None
        if any(a.get('destination_root','workspace')!='workspace' for a in actions):return None
        if any(a.get('source_root','workspace')!='workspace' for a in suffix):return None
        if any(not isinstance(a.get('file_ids'),list) or len(a['file_ids'])!=1 for a in suffix):return None
        return prefix,suffix
    left,right=partition(actual),partition(expected)
    if not left or not right or left[0]!=right[0]:return None
    if sorted(digest(a) for a in left[1])!=sorted(digest(a) for a in right[1]):return None
    def relative(path):
        if not isinstance(path,str) or '\\' in path or path.startswith('/'):return None
        parts=path.split('/')
        return path if all(p not in ('','..','.') for p in parts) else None
    inventory=source['context']['receipts'].get('mcp__file_management__list_files',{}).get('files',[])
    files={r['file_id']:r for r in inventory}
    if len(files)!=len(inventory):return None
    current=set()
    for row in inventory:
        if row.get('root_id','workspace')!='workspace':continue
        path=row.get('path','').removeprefix('workspace/')
        if relative(path) is None:return None
        current.add(path)
    directories={relative(a.get('destination')) for a in left[0]}
    if None in directories:return None
    targets=[];inputs=[]
    for action in left[1]:
        row=files.get(action['file_ids'][0]);target=relative(action.get('destination'))
        if not row or row.get('root_id','workspace')!='workspace' or target is None:return None
        if target in directories:return None
        if any(target==p or target.startswith(p+'/') or p.startswith(target+'/') for p in current):return None
        if any(target==p or target.startswith(p+'/') or p.startswith(target+'/') for p in targets):return None
        targets.append(target);inputs.append({'file_id':row['file_id'],'sha256':row['sha256']})
    return {'kind':'disjoint_new_workspace_copy_permutation_v2',
        'mkdir_prefix_sha256':digest(left[0]),'copy_action_multiset_sha256':digest(sorted(digest(a) for a in left[1])),
        'source_inventory_sha256':digest(inventory),'source_versions':inputs,'new_targets':sorted(targets),
        'requires_independent_goal_order_review':True,'task_quality_and_permissions_unchanged':True,
        'original_order_preserved_in_source':True,'generated_order_unchanged':True}
