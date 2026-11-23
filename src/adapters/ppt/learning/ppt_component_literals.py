"""Classify interface keys and non-text SVG palette values for certification."""
import ast
import json
from pathlib import Path
import re
import sys
import xml.etree.ElementTree as ET


def technical_literals(source, svg):
    tree = ast.parse(source)
    parents = {child: parent for parent in ast.walk(tree) for child in ast.iter_child_nodes(parent)}
    uses = {}
    for node in ast.walk(tree):
        if not isinstance(node, ast.Constant) or not isinstance(node.value, str):
            continue
        parent = parents.get(node)
        key = isinstance(parent, ast.Subscript) and parent.slice is node
        key = key or (isinstance(parent, ast.Call) and isinstance(parent.func, ast.Attribute) and
                      parent.func.attr == 'get' and parent.args and parent.args[0] is node)
        uses.setdefault(node.value, []).append(bool(key))
    keys = {text for text, roles in uses.items() if all(roles)}
    root = ET.fromstring(svg)
    visible = '\n'.join(''.join(node.itertext()) for node in root.iter()
                        if node.tag.rsplit('}', 1)[-1] == 'text')
    palette = set()
    for node in root.iter():
        attributes = dict(node.attrib)
        for declaration in node.get('style', '').split(';'):
            if ':' in declaration:
                name, value = declaration.split(':', 1)
                attributes[name.strip()] = value.strip()
        for name in ('fill', 'stroke', 'stop-color', 'color'):
            value = attributes.get(name, '')
            if re.fullmatch(r'#[0-9a-fA-F]{3}(?:[0-9a-fA-F]{3})?', value) and value not in visible:
                palette.add(value)
    return {'interface_keys': sorted(keys), 'presentation_palette': sorted(palette)}


if __name__ == '__main__':
    request = json.load(sys.stdin)
    print(json.dumps(technical_literals(request['source'], Path(request['reference']).read_bytes())))
