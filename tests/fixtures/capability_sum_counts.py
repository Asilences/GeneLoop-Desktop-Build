"""Fixed diagnostic successor: consumes both predecessor outputs, no model/API."""
import json
import sys

value = json.load(sys.stdin)
left, right = value['left'], value['right']
print(json.dumps({'counts': {
    key: left.get(key, 0) + right.get(key, 0)
    for key in sorted(left.keys() | right.keys())
}}, separators=(',', ':')))
