"""Execution view of existing cards; full native records stay in the bundle."""
import copy
import re


def opaque_type_hints(native, observed, pointer=''):
    """Deduplicate already-computed type metadata, without reading input values."""
    if not isinstance(observed, dict):
        return {}
    # A heterogeneous record union describes possible observed shapes, even
    # when the native contract expands an object. Keep its correlations intact.
    if 'union' in observed:
        return {pointer: observed}
    if isinstance(native, str):
        return {pointer: observed} if native in ('object', 'array') and isinstance(observed, dict) else {}
    if not isinstance(native, dict):
        return {}
    hints = {}
    if 'object' in native:
        for key, child in native['object'].items():
            escaped = key.replace('~', '~0').replace('/', '~1')
            hints.update(opaque_type_hints(child, observed.get('object', {}).get(key),
                                           pointer + '/' + escaped))
    elif 'array' in native:
        hints.update(opaque_type_hints(native['array'], observed.get('array'), pointer + '/*'))
    return hints


def execution_card(card):
    contracts = card.get('native_input_contracts', card['input_contracts'])
    parameters = card.get('parameter_interface', {})
    shapes = card.get('observed_json_shapes', parameters.get('observed_json_shapes', []))
    document = card.get('input_documentation', '')
    # Keep the source-authored interface, including option semantics. Its intro
    # and operation description are already present verbatim in the menu.
    document = re.split(r'\n(?:JSON|Input) interface\n[-=]+\n', document, maxsplit=1, flags=re.I)[-1]
    document = '\n'.join(line.strip() for line in document.splitlines() if line.strip())
    view = {'id': card['id'], 'input_schema': card['input_schema'],
        'input_roles': card.get('input_roles', []), 'input_contracts': contracts,
        'field_documentation': document,
        'observed_opaque_types': {str(index): opaque_type_hints(contract['shape'], shapes[index])
            for index, contract in enumerate(contracts) if index < len(shapes)},
        'type_scope': 'Native contracts govern admission. Observed types show possible observed shapes; '
            'they are not extra required fields or proof of visual suitability.',
        'source_path': card['source_path'],
        'outputs': [item['path'] if isinstance(item, dict) else item for item in card['output_files']]}
    if card.get('native_binding') == 'artifact_json_values':
        # The JSON bodies are already described by input_contracts. Show the
        # outer call and slot types once; the full native schema stays in audit.
        view['input_schema'] = copy.deepcopy(card['input_schema'])
        values = view['input_schema']['properties']['values']
        values['properties'] = {slot: {'type': schema['type']} if 'type' in schema else schema
            for slot, schema in values.get('properties', {}).items()}
        view['binding_scope'] = 'Pass current JSON objects directly in values slots. '
        view['binding_scope'] += 'input_contracts give their native body constraints in slot order; no input-file writing is needed.'
        if card.get('file_interface_id'):
            view['file_interface_id'] = card['file_interface_id']
    # Binding rules and model-selected extensions remain visible exactly once.
    rules = {key: value for key, value in parameters.items()
        if key not in ('observed_json_shapes', 'scope', 'keyword_groups')}
    # source_origin records how an old input was witnessed; the scene adapter
    # handles that projection. It does not change the JSON key/type contract.
    def contract_view(items):
        return [{key: value for key, value in item.items() if key != 'source_origin'} for item in items]
    if 'input_role_contracts' in rules and contract_view(rules['input_role_contracts']) == contract_view(contracts):
        del rules['input_role_contracts']
    if rules.get('parameter_file_required') is False:
        rules.pop('parameter_path', None)
        if not rules.get('defaults'):
            rules.pop('defaults', None)
        if not rules.get('parameters_schema', {}).get('properties'):
            rules.pop('parameters_schema', None)
    if rules:
        view['parameter_interface'] = rules
    if card.get('compiled_keyword_groups'):
        view['compiled_keyword_groups'] = card['compiled_keyword_groups']
    return view
