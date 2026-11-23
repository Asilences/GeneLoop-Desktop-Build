"""Mechanical lexical-binding notation, with no task logic or host execution."""
import copy

VERSION='lexical-bindings-v2'
PREVIOUS_VERSION='lexical-bindings-v1'
# Previously published compiler identities used when replaying a proof.
REPLAY_DIGESTS={
    'b727ae8ba2474b538d53d144f55ea95917d5238299e6472447046c97440b5848':'lexical-bindings-v2',
    'f4e77a595c54d58c1042f8006735612b9b9e5e65494a85e1fa4f7dd6ee02a52f':'lexical-bindings-v1',
}

INSTRUCTIONS='''For guard/request/bind component ROOTS use lexical binding blocks instead of deeply nested let arrays:
{"bindings":[{"name":"x","value":["get",["var","input"],["lit","some_actual_field"]]}],"result":["var","x"]}.
Every binding has exactly name/value. Bindings execute in list order; result is the body after all bindings.
Blocks can occur anywhere an expression is expected, including map/filter bodies and binding values.
All other expressions use the original pure interpreter operations. The compiler only lowers bindings to nested four-member let arrays, preserving variable scope and expression order. It never supplies task routes, decisions, missing expressions or values. Literal data inside lit is untouched.
Prefer bindings blocks for every nontrivial local scope; never write malformed multi-member let lists.'''
INSTRUCTIONS+=''' Plain JSON records in expression positions are object builders whose field values are expressions. Bare string/number/bool/null expressions are literals. Explicit lit data is always preserved verbatim; it is never interpreted as a binding block or executable expression.'''


def expression_schema():
    return {'type':'object','properties':{
        'bindings':{'type':'array','items':{'type':'object','properties':{
            'name':{'type':'string'},'value':{}},'required':['name','value'],'additionalProperties':False}},
        'result':{}},'required':['bindings','result'],'additionalProperties':False}


def lower_program(value,*,version=VERSION):
    if version not in (VERSION,PREVIOUS_VERSION):
        raise ValueError('unknown lowering compiler version')
    return _lower_program(value,version)


def _lower_program(value,version):
    if isinstance(value,dict):
        if version==PREVIOUS_VERSION and (set(value)!={'bindings','result'} or not isinstance(value['bindings'],list)):
            raise ValueError('binding block requires bindings and result')
        if set(value)!={'bindings','result'}:
            return ['object',{k:_lower_program(v,version)for k,v in value.items()}]
        if not isinstance(value['bindings'],list):raise ValueError('bindings must be an ordered list')
        result=_lower_program(value['result'],version)
        for binding in reversed(value['bindings']):
            if not isinstance(binding,dict) or set(binding)!={'name','value'} or not isinstance(binding['name'],str):
                raise ValueError('binding requires explicit name and value')
            result=['let',binding['name'],_lower_program(binding['value'],version),result]
        return result
    if version==PREVIOUS_VERSION and (not isinstance(value,list) or not value):return copy.deepcopy(value)
    if not isinstance(value,list):return ['lit',copy.deepcopy(value)]
    if not value:return ['array']
    op=value[0]
    if op in ('lit','var'):return copy.deepcopy(value)
    if op=='object' and len(value)==2 and isinstance(value[1],dict):
        return [op,{k:_lower_program(v,version)for k,v in value[1].items()}]
    return [op,*[copy.deepcopy(v)if (op=='let' and i==1 or op in ('map','filter') and i==2)
                 else _lower_program(v,version)for i,v in enumerate(value[1:],1)]]


def lower_patch(patch,*,version=VERSION):
    return {k:lower_program(v,version=version)if k in ('guard','request','bind')else copy.deepcopy(v)for k,v in patch.items()}
