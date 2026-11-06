"""Deterministic diagnostic operations, executed by the real Capability Runtime."""
import json
import sys

value = json.load(sys.stdin)['value']
operations = {'increment': lambda x: x + 1, 'double': lambda x: 2 * x, 'subtract': lambda x: x - 3}
json.dump({'value': operations[sys.argv[1]](value)}, sys.stdout)
