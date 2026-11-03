"""Bind a new helper's native probes from its model-selected certified prefix.

This is offline input preparation, not a new evaluator or certificate. A
candidate prefix receives the existing native validation grant; all selected
dependencies remain certified, read-only, current and version-pinned.
"""
from __future__ import annotations

import copy
import hashlib
import json
from pathlib import Path

from jsonschema import Draft202012Validator

from src.adapters.capability_builder import compile_proposal, _check_binding
from src.adapters.capability_authoring import diagnose
from src.adapters.capability_contract import capability_digest, capability_ref, validate_capability_snapshot
from src.adapters.capability_improvement import evidence, save
from src.adapters.capability_scene import reference
from src.adapters.capability_shape_diagnostics import composition_shape_advisories,diagnose_step_argument_shapes
from scenarios.paper_proofreading.frontier.execute import execute


class TrainingEvidenceUnavailable(ValueError):
    """The host did not provide independent training inputs for this binding."""


def _prefix_failure(error,candidate,case,directory):
    """Keep verified failure sources separate from advisory binding observations."""
    detail={'kind':'construction_prefix','error':str(error).split(':',1)[0],
        'failed_case':case['id'],'scope':'Diagnostics only; no certificate, contract change or retry authorization',
        'sources':[],'worker_failures':[],'shape_advisories':composition_shape_advisories(candidate)}
    for name in ('trace.json','stderr.log','manifest.json','args.json','snapshot.json'):
        path=directory/name
        if path.is_file():detail['sources'].append(reference(path))
    try:trace=json.loads((directory/'trace.json').read_text())
    except (OSError,ValueError):trace={}
    receipts={row.get('call_id'):row for row in trace.get('receipts',[]) if isinstance(row,dict)}
    root=next((row for row in receipts.values() if row.get('capability')==capability_ref(candidate['capability']) and row.get('parent_call_id') is None),{})
    steps=candidate['capability']['implementation']['steps']
    capabilities={cap['id']:cap for cap in candidate['snapshot']['capabilities']}
    direct={call:steps[index] for index,call in enumerate(root.get('child_call_ids',[])) if index<len(steps)}
    for path in sorted(directory.glob('work/calls/*/failure.json')):
        ref=reference(path);detail['sources'].append(ref)
        try:failure=json.loads(evidence(ref))
        except ValueError:continue
        receipt=receipts.get(path.parent.name);step=direct.get(path.parent.name)
        called=capabilities.get((receipt or {}).get('capability',{}).get('id'),{})
        matched=(failure.get('format')=='script_capability_call_failure_v1' and receipt is not None
            and failure.get('call_id')==receipt.get('call_id') and failure.get('capability')==receipt.get('capability')
            and failure.get('arguments_sha256')==receipt.get('arguments_sha256') and receipt.get('reason')=='script_worker_failed'
            and called.get('implementation',{}).get('legacy_ref',{}).get('backend')=='script_motif')
        row={'evidence':ref,'verified_call_binding':matched,'diagnostic':failure.get('diagnostic') if matched else None}
        value_file=path.parent/'inputs/value.json'
        schema=capabilities[step['capability']['id']]['contract']['input_schema'] if step is not None else {}
        value_call=(schema.get('required')==['value'] and set(schema.get('properties',{}))=={'value'})
        if matched and step is not None and value_call and value_file.is_file():
            raw=value_file.read_bytes();versions=failure.get('input_versions',[])
            outer_sha=hashlib.sha256(b'{"value":'+raw+b'}').hexdigest()
            if versions==[hashlib.sha256(raw).hexdigest()] and outer_sha==receipt.get('arguments_sha256'):
                try:
                    payload=json.loads(raw);arguments={'value':payload}
                    row.update(arguments_evidence=reference(value_file),
                        argument_shapes=diagnose_step_argument_shapes(candidate,step['id'],arguments))
                except (ValueError,KeyError,TypeError):row['argument_shape_unavailable']=True
        detail['worker_failures'].append(row)
    return detail


def _input_binding(binding, current):
    """The zero-call subset of the existing IR, without Python evaluation."""
    kind=binding['kind']
    if kind=='literal':return copy.deepcopy(binding['value'])
    if kind=='input':
        result=current
        for key in binding['path']:
            if not isinstance(result,dict) or key not in result:raise ValueError('frontier_training_input_path_missing')
            result=result[key]
        return copy.deepcopy(result)
    if kind=='object':return {key:_input_binding(child,current) for key,child in binding['fields'].items()}
    if kind=='array':return [_input_binding(child,current) for child in binding['items']]
    raise ValueError('frontier_training_prefix_step_missing')


def prepare_program_cases(task,snapshot,program_ref,intent_ref,construction_cases,libraries,directory,*,source_refs=()):
    """Return exactly two JSON probes whose values came from the frozen graph.

    No final-test case, precomputed oracle value, source-text example, or model
    claim is substituted for a runtime result. All call arguments remain the
    bindings explicitly selected before native material acquisition.
    """
    if construction_cases is None:raise TrainingEvidenceUnavailable('frontier_program_construction_cases_required')
    if not isinstance(construction_cases,list) or len(construction_cases)!=2:
        raise TrainingEvidenceUnavailable('frontier_program_two_training_cases_required')
    snapshot=validate_capability_snapshot(snapshot)
    program=json.loads(evidence(program_ref));intent=json.loads(evidence(intent_ref))
    capability_digest(intent)
    if (intent.get('format')!='capability_program_composition_intent_v1' or intent.get('owner')!=snapshot['owner']
            or intent.get('construction_snapshot_sha256')!=snapshot['digest']
            or intent.get('task_sha256')!=capability_digest(task) or intent.get('program_sha256')!=capability_digest(program)):
        raise ValueError('frontier_training_intent_changed')
    if program.get('mode')!='json':raise ValueError('frontier_training_json_helper_required')
    slots=[index for index,step in enumerate(intent['steps']) if step['capability']=='$program']
    if len(slots)!=1:raise ValueError('frontier_training_single_program_call_required')
    index=slots[0];selected=intent['steps'][index];arguments=selected['arguments']
    if arguments.get('kind')!='object' or set(arguments.get('fields',{}))!={'value'}:
        raise ValueError('frontier_training_program_value_binding_required')
    payload=arguments['fields']['value'];steps=copy.deepcopy(intent['steps'][:index])
    lookup={cap['id']:cap for cap in snapshot['capabilities']}
    for step in steps:
        if step['capability'] not in snapshot['roots']:raise ValueError('frontier_training_reference_not_visible')
        cap=lookup[step['capability']['id']]
        if cap['certification']!='certified' or cap['lifecycle']!='active' or set(cap['contract']['effects'])-{'read'}:
            raise ValueError('frontier_training_dependency_not_readonly_certified')
    # Validate the entire case inventory before executing any prefix.
    for case in construction_cases:
        if not isinstance(case,dict) or set(case)!={'id','split','input','inputs'} or case['split']!='training':
            raise TrainingEvidenceUnavailable('frontier_program_training_split_required')
        Draft202012Validator(task['contract']['input_schema']).validate(case['input'])
        if not isinstance(case['inputs'],list):raise ValueError('frontier_training_inputs_invalid')
        for item in case['inputs']:evidence(item['source'])
    for ref in [*libraries,*source_refs]:evidence(ref)
    directory=Path(directory);directory.mkdir(parents=True,exist_ok=False,mode=0o700)
    record={'format':'capability_program_training_v1','scope':'Actual certified prefix on host training cases; no semantic quality verdict',
        'task_sha256':capability_digest(task),'construction_snapshot_sha256':snapshot['digest'],
        'program':program_ref,'intent':intent_ref,'source_evidence':list(source_refs),'cases':[]}
    save(directory/'construction-cases.json',construction_cases)
    record['construction_cases']=reference(directory/'construction-cases.json')
    candidate=None
    if steps:
        proposal={'format':'capability_compose_proposal_v1','owner':snapshot['owner'],
            'contract':{'input_schema':copy.deepcopy(task['contract']['input_schema']),'output_schema':{},'effects':['read']},
            'steps':steps,'output':copy.deepcopy(payload)}
        save(directory/'prefix-proposal.json',proposal)
        try:candidate=compile_proposal(proposal,snapshot,snapshot['owner'])
        except Exception as error:
            detail={'kind':'construction_prefix_compile','error':str(error),'diagnostics':diagnose(error),
                'proposal':reference(directory/'prefix-proposal.json'),'intent':intent_ref,'program':program_ref}
            save(directory/'failure.json',detail)
            error.program_training_diagnostics=detail;error.program_training_evidence_ref=reference(directory/'failure.json')
            raise
        save(directory/'prefix-candidate.json',candidate)
        record['prefix_candidate']=reference(directory/'prefix-candidate.json')
    else:
        _check_binding(payload,{},task['contract']['input_schema'],{},('program','arguments','value'))
    native_cases=[]
    for number,case in enumerate(construction_cases):
        local=directory/('case-'+str(number));local.mkdir(mode=0o700)
        if candidate:
            try:
                trace=execute(candidate['snapshot'],capability_ref(candidate['capability']),libraries,case['inputs'],
                    case['input'],local/'prefix','training-prefix-'+str(number),mode='validate')
            except Exception as error:
                detail=_prefix_failure(error,candidate,case,local/'prefix')
                detail.update(prefix_candidate=record['prefix_candidate'],intent=intent_ref,program=program_ref)
                record.update(status='failed',failed_case=case['id'],diagnostics=detail)
                save(directory/'failure.json',record)
                error.program_training_diagnostics=detail;error.program_training_evidence_ref=reference(directory/'failure.json')
                raise
            value=trace['result'];trace_ref=reference(local/'prefix/trace.json')
        else:
            value=_input_binding(payload,case['input']);trace_ref=None
        # Canonical bytes are the exact payload consumed by the native helper.
        raw=json.dumps(value,ensure_ascii=False,sort_keys=True,separators=(',',':'),allow_nan=False).encode('utf-8')
        path=local/'value.json';path.write_bytes(raw);path.chmod(0o400)
        row={'id':case['id'],'split':'training','task_input_sha256':capability_digest(case['input']),
            'input_versions':copy.deepcopy(case['inputs']),'value':reference(path),'prefix_trace':trace_ref,
            'origin':'candidate_validation_of_certified_dependencies' if candidate else 'explicit_input_or_literal_binding_no_calls'}
        record['cases'].append(row)
        native_cases.append({'id':case['id']+'-helper','inputs':[{'path':'/work/inputs/value.json','source':reference(path)}]})
    save(directory/'result.json',record)
    return {'cases':native_cases,'evidence':reference(directory/'result.json')}
