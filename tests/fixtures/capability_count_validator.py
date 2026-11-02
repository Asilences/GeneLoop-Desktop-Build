"""Independent mechanical checker for synthetic store diagnostics, not real quality."""
import collections
import json
import sys
value=json.load(sys.stdin)
expected=dict(collections.Counter(row['group'] for row in value['input']['rows']))
actual=json.loads(value['artifact'])
passed=actual=={'counts':expected}
print(json.dumps({'passed':passed,'checks':[{'id':'count-exact','status':'passed' if passed else 'failed','observation':'Compared artifact bytes with independently recomputed input counts.'}]}))
