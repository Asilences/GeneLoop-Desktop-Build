"""Opt-in Builder self-application, through the SAME Capability graph learner.

Host adapters supply real Runtime execution and certified references. This module
does not create capabilities, grant certificates, publish, or modify an evaluator.
The first release independently replays the old encoder before accepting a result;
that is conformance evidence, NOT a claim of lower construction cost.
"""
from __future__ import annotations
import copy
import json
from pathlib import Path

from .capability_contract import capability_digest, validate_capability_snapshot
from .capability_feedback import file_ref
from .capability_improvement import evidence, save


def _json(value):
    capability_digest(value)
    return json.dumps(value, ensure_ascii=False, allow_nan=False, separators=(',', ':'))


def builder_operation(operation, arguments):
    """Two allowlisted, actual operations of prepare_capability_source_request.

    Only a trusted native adapter invokes this function. No evaluator, permission,
    registry or file mutation operation is exposed to generated source.
    """
    from .capability_source_authoring import compile_source_draft, freeze_source_draft
    if operation == 'builder_parse':
        if set(arguments) != {'context_json'}: raise ValueError('builder_parse_arguments')
        context = json.loads(arguments['context_json'])
        if set(context) != {'draft', 'task', 'snapshot', 'catalog'}: raise ValueError('builder_context_fields')
        encoded = compile_source_draft(context['draft'], context['task'], context['snapshot'], context['catalog'])
        return {'prepared_json': _json({'context': context, 'encoded': encoded})}
    if operation == 'builder_freeze':
        if set(arguments) != {'prepared_json'}: raise ValueError('builder_freeze_arguments')
        value = json.loads(arguments['prepared_json'])
        context = value['context']
        return {'result_json': _json(freeze_source_draft(value['encoded'], context['task'], context['snapshot']))}
    raise ValueError('builder_operation_not_allowed')


def _bind(binding, value):
    if binding.get('kind') == 'input':
        for key in binding['path']: value = value[key]
        return copy.deepcopy(value)
    if binding.get('kind') == 'object': return {k: _bind(v, value) for k, v in binding['fields'].items()}
    if binding.get('kind') == 'literal': return copy.deepcopy(binding['value'])
    raise ValueError('builder_application_binding_invalid')


class BuilderConstructionSession:
    """Trusted host hook for the existing Builder's static compilation stage.

    execute(ref, arguments, directory, task_id) must run the original Runtime and
    return an immutable execution_ref. No fabricated input/output substitutes.
    learned_selection is host-frozen {root,input_binding,result_path}; disabled
    sessions do not read these references or run any extra operations.
    """
    def __init__(self, *, enabled=False, snapshot=None, parse_ref=None, freeze_ref=None,
                 execute=None, directory=None, task_id=None, learned_selection=None):
        self.enabled = enabled
        self.snapshot = copy.deepcopy(snapshot)
        self.parse_ref, self.freeze_ref = copy.deepcopy(parse_ref), copy.deepcopy(freeze_ref)
        self.execute, self.directory, self.task_id = execute, directory, task_id
        self.learned = copy.deepcopy(learned_selection)

    def prepare(self, draft, task, snapshot, catalog, *, ordinary):
        if not self.enabled: return ordinary()
        from .capability_motif_learning import capture_capability_trace
        library = validate_capability_snapshot(self.snapshot, snapshot['owner'])
        directory = Path(self.directory)
        directory.mkdir(parents=True, exist_ok=False, mode=0o700)
        context = {'draft': draft, 'task': task, 'snapshot': snapshot, 'catalog': catalog}
        task_input = {'context_json': _json(context)}
        save(directory/'input.json', task_input)
        record = {'format': 'capability_builder_application_v1', 'task_id': self.task_id,
                  'owner': snapshot['owner'], 'input': file_ref(directory/'input.json'),
                  'status': 'started', 'learned_selection': self.learned,
                  'model_requests': 0, 'model_cost': '0', 'total_cost': None,
                  'efficiency_conclusion': None, 'trace': None}
        save(directory/'started.json', record)
        calls = []
        def invoke(call_id, root, binding, args):
            if root not in library['roots']: raise ValueError('builder_application_unavailable')
            ref = self.execute(root, args, directory/call_id, self.task_id)
            row = {'id': call_id, 'capability': root, 'input_binding': binding, 'execution_ref': ref}
            calls.append(row)
            outcome = json.loads(evidence(ref))
            if outcome.get('status') in ('cancelled', 'interrupted'):
                raise KeyboardInterrupt('builder_application_interrupted')
            if outcome.get('status') != 'succeeded': raise ValueError('builder_application_execution_failed')
            return outcome['result']
        try:
            if self.learned is None:
                parsed = invoke('parse', self.parse_ref,
                                {'kind': 'object', 'fields': {'context_json': {'kind': 'input', 'path': ['context_json']}}}, task_input)
                result = invoke('freeze', self.freeze_ref,
                                {'kind': 'object', 'fields': {'prepared_json': {'kind': 'step', 'step_id': 'parse', 'path': ['prepared_json']}}}, parsed)
                result = result['result_json']
            else:
                selection = self.learned
                if set(selection) != {'root', 'input_binding', 'result_path'}:
                    raise ValueError('builder_application_selection_invalid')
                result = invoke('learned', selection['root'], selection['input_binding'],
                                _bind(selection['input_binding'], task_input))
                for part in selection['result_path']: result = result[part]
            trace = capture_capability_trace(library, task_id=self.task_id, task_input=task_input,
                task_fingerprint=capability_digest(context), calls=calls, role='builder')
            save(directory/'trace.json', trace)
            record['trace'] = file_ref(directory/'trace.json')
            value = json.loads(result)
            expected = ordinary()  # host check; candidates cannot replace it
            if capability_digest(value) != capability_digest(expected):
                raise ValueError('builder_application_independent_check_failed')
            record.update(status='accepted', behavior='learned_composition' if self.learned else 'observed_original_stages')
            save(directory/'result.json', record)
            return value
        except (KeyboardInterrupt, SystemExit):
            record.update(status='interrupted', calls=calls)
            save(directory/'result.json', record)
            raise
        except Exception as error:
            record.update(status='fallback', error=type(error).__name__+':'+str(error).split(':')[0], calls=calls)
            save(directory/'result.json', record)
            return ordinary()


if __name__ == '__main__':
    import sys
    request = json.load(sys.stdin)
    print(_json(builder_operation(request['operation'], request['arguments'])))
