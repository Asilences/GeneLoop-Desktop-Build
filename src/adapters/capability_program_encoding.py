"""Encode a model's complete Script solver into the frozen task interface.

No algorithm is synthesized or repaired here. Only an exact witnessed input
name match and a statically compatible output permit a one-step candidate.
Native certification and independent semantic publication remain mandatory.
"""
import json
from pathlib import PurePosixPath
from .capability_improvement import evidence
from .capability_contract import capability_ref
from .capability_builder import compile_proposal


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
