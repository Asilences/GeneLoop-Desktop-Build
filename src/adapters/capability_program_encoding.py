"""Encode a model's complete Script solver into the frozen task interface.

No algorithm is synthesized or repaired here. Only an exact witnessed input
name match and a statically compatible output permit a one-step candidate.
Native certification and independent semantic publication remain mandatory.
"""
import copy
import hashlib
import json
from pathlib import PurePosixPath
from .capability_improvement import evidence
from .capability_contract import capability_ref, capability_digest, validate_capability_snapshot
from .capability_builder import compile_proposal
from .capability_authoring import aliases, expand_binding, compact_binding, AuthoringError


PROGRAM_SLOT = '$program'
INTENT_FORMAT = 'capability_program_composition_intent_v1'


def freeze_program_composition(task, snapshot, program, composition):
    """Pin model choices before acquisition can reorder visible aliases.

    This records bindings; it neither finds an implementation nor connects an
    unbound input. The only unresolved reference is the explicit new-program
    slot. Its algorithm must independently pass native certification later.
    """
    snapshot=validate_capability_snapshot(snapshot)
    capability_digest(composition)
    if not isinstance(composition,dict) or set(composition)!={'steps','output'}:
        raise AuthoringError('draft_shape',['composition'],{'keys':['steps','output']},composition)
    rows=composition['steps'];table=aliases(snapshot);steps=[]
    if not isinstance(rows,list) or not 1<=len(rows)<=64:
        raise AuthoringError('draft_steps',['composition','steps'],'array of 1..64 steps',rows)
    for index,step in enumerate(rows):
        path=['composition','steps',index]
        if not isinstance(step,dict) or set(step)!={'id','use','args'}:
            raise AuthoringError('draft_shape',path,{'keys':['id','use','args']},step)
        use=step['use']
        if use!=PROGRAM_SLOT and (not isinstance(use,str) or use not in table):
            raise AuthoringError('reference_not_visible',path+['use'],[PROGRAM_SLOT,*table],use)
        steps.append({'id':step['id'],'capability':PROGRAM_SLOT if use==PROGRAM_SLOT else copy.deepcopy(table[use]),
            'arguments':expand_binding(step['args'],path+['args'])})
    if not any(step['capability']==PROGRAM_SLOT for step in steps):
        raise AuthoringError('program_slot_missing',['composition','steps'],'at least one explicit $program use',composition)
    return {'format':INTENT_FORMAT,'owner':snapshot['owner'],
        'construction_snapshot_sha256':snapshot['digest'],'task_sha256':capability_digest(task),
        'program_sha256':capability_digest(program),'steps':steps,
        'output':expand_binding(composition['output'],['composition','output'])}


def encode_program_composition(task,snapshot,program_ref,intent_ref,library_ref,observations_ref):
    """Replace only a frozen $program with its exact certified material ref."""
    snapshot=validate_capability_snapshot(snapshot)
    program=json.loads(evidence(program_ref));intent=json.loads(evidence(intent_ref))
    library=json.loads(evidence(library_ref));observations=json.loads(evidence(observations_ref))
    keys={'format','owner','construction_snapshot_sha256','task_sha256','program_sha256','steps','output'}
    if not isinstance(intent,dict) or set(intent)!=keys or intent['format']!=INTENT_FORMAT:
        raise ValueError('program_composition_intent_invalid')
    if intent['owner']!=snapshot['owner'] or intent['task_sha256']!=capability_digest(task) or intent['program_sha256']!=capability_digest(program):
        raise ValueError('program_composition_context_changed')
    source_sha=hashlib.sha256(program['source'].encode('utf-8')).hexdigest()
    mode=program.get('mode');required=['value'] if mode=='json' else ['paths'] if mode=='paths' else None
    if required is None:raise ValueError('program_composition_mode_invalid')
    witnessed=[candidate for row in observations for candidate in row.get('candidates',[])]
    certified=[]
    for native in library['programs']:
        witnesses=[row for row in witnessed if row['id']==native['id']]
        if native.get('certification',{}).get('passed') is not True or len(witnesses)!=1:
            continue
        if witnesses[0].get('witness',{}).get('model_source_sha256')!=source_sha:
            continue
        for cap in snapshot['capabilities']:
            if capability_ref(cap) not in snapshot['roots'] or cap['implementation']['kind']!='legacy':continue
            legacy=cap['implementation']['legacy_ref']
            if (legacy.get('backend')=='script_motif' and legacy.get('library_sha256')==library_ref['sha256']
                    and legacy.get('object_id')==native['id'] and cap['certification']=='certified'
                    and cap['lifecycle']!='archived' and cap['contract']['input_schema'].get('required')==required):
                certified.append(capability_ref(cap))
    if len(certified)!=1:raise ValueError('program_composition_certified_material_missing_or_ambiguous')
    proposal={'format':'capability_compose_proposal_v1','owner':snapshot['owner'],
        'contract':copy.deepcopy(task['contract']),'steps':copy.deepcopy(intent['steps']),'output':copy.deepcopy(intent['output'])}
    used=False
    for step in proposal['steps']:
        if step['capability']==PROGRAM_SLOT:
            step['capability']=copy.deepcopy(certified[0]);used=True
        elif step['capability'] not in snapshot['roots']:
            raise ValueError('program_composition_existing_reference_not_visible')
    if not used:raise ValueError('program_composition_program_slot_missing')
    try:candidate=compile_proposal(proposal,snapshot,snapshot['owner'])
    except ValueError as error:
        # Keep the failed bindings visible while rebasing only their reference
        # spelling. Never pretend this invalid graph is a compiled proposal.
        reverse={ref['id']:name for name,ref in aliases(snapshot).items()}
        error.program_composition_repair_context={
            'format':'capability_program_composition_repair_v1',
            'current_snapshot_sha256':snapshot['digest'],
            'originating_snapshot_sha256':intent['construction_snapshot_sha256'],
            'scope':'Frozen model choices with current alias spellings; bindings remain invalid and unrepaired. No dependency or argument was added.',
            'steps':[{'id':step['id'],'capability':copy.deepcopy(step['capability']),
                'current_alias':reverse[step['capability']['id']],
                'arguments':compact_binding(step['arguments'])} for step in proposal['steps']],
            'output':compact_binding(proposal['output'])}
        raise
    return {'proposal':proposal,'candidate':candidate,'source_program_id':next(
        cap['implementation']['legacy_ref']['object_id'] for cap in snapshot['capabilities'] if capability_ref(cap)==certified[0]),
        'encoding_scope':'model_explicit_composition_fixed_before_certification_only_program_slot_resolved'}


def encode_complete_script(task,snapshot,library_ref,observations_ref):
    library=json.loads(evidence(library_ref));rows=json.loads(evidence(observations_ref))
    inputs=task['contract']['input_schema'];required=inputs.get('required',[])
    if inputs.get('type')!='object' or set(inputs.get('properties',{}))!=set(required):return None
    if not required or any(inputs['properties'][key].get('type')!='string' for key in required):return None
    candidates=[p for row in rows for p in row.get('candidates',[])]
    for program in library['programs']:
        witnesses=[p for p in candidates if p['id']==program['id']]
        if len(witnesses)!=1:continue
        witness=witnesses[0];names=[]
        for path in witness['original_paths']:
            relative=witness['witness']['files'][path]['relative']
            if PurePosixPath(relative).parent!=PurePosixPath('inputs'):break
            names.append(PurePosixPath(relative).stem)
        if len(names)!=len(program['inputs']) or len(set(names))!=len(names) or set(names)!=set(required):continue
        visible=[]
        for cap in snapshot['capabilities']:
            if capability_ref(cap) not in snapshot['roots'] or cap['implementation']['kind']!='legacy':continue
            legacy=cap['implementation']['legacy_ref']
            if legacy.get('backend')=='script_motif' and legacy.get('library_sha256')==library_ref['sha256'] and legacy.get('object_id')==program['id']:
                if cap['contract']['input_schema'].get('required')==['paths']:visible.append(cap)
        if len(visible)!=1:continue
        proposal={'format':'capability_compose_proposal_v1','owner':snapshot['owner'],'contract':task['contract'],
            'steps':[{'id':'program','capability':capability_ref(visible[0]),'arguments':{'kind':'object','fields':{
                'paths':{'kind':'array','items':[{'kind':'input','path':[name]} for name in names]}}}}],
            'output':{'kind':'step','step_id':'program','path':['value']}}
        try:candidate=compile_proposal(proposal,snapshot,snapshot['owner'])
        except ValueError:continue
        return {'proposal':proposal,'candidate':candidate,'source_program_id':program['id'],
            'encoding_scope':'mechanical_witnessed_file_slots_and_JSON_result_wrapper_not_semantic_certification'}
    return None
