"""Pure IR constructors in Python notation. Parses data; never executes Python."""
import ast
import copy

VERSION='pure-constructors-v4'
PREVIOUS_VERSION='pure-constructors-v3'
# Previously published compiler identities used when replaying a proof.
REPLAY_DIGESTS={
    '2a9ed9a3bd1024e0702646a4dba3af3d275e2b617e837303209d9e255f9abbc2':'pure-constructors-v4',
    '9c48fc5d056ff544744a5def31c461bd04f58400f7438bb71bb160deaafaf78b':'pure-constructors-v3',
}

OPS={'get','array','map','filter','unique','difference','concat','count','eq','not','and','or','if','type','gt','join','let','sort','split','at','keys'}

def bound_expression(program,name):
    """Import an existing lexical value with its original enclosing bindings."""
    prefix=[];node=program
    while isinstance(node,list)and len(node)==4 and node[0]=='let':
        prefix.append(node[:3])
        if node[1]==name:
            result=['var',name]
            for binding in reversed(prefix):result=[*copy.deepcopy(binding),result]
            return result
        node=node[3]
    raise ValueError('prototype has no outer binding: '+name)

def construct(source,prototypes=None,*,version=VERSION):
    if version not in (VERSION,PREVIOUS_VERSION):raise ValueError('unknown construction compiler version')
    env={}
    def plain(node):
        return ast.literal_eval(node)
    def expr(node):
        if isinstance(node,ast.Name):
            if node.id not in env:raise ValueError('undeclared construction name: '+node.id)
            return copy.deepcopy(env[node.id])
        if isinstance(node,ast.Constant):return ['lit',node.value]
        if isinstance(node,ast.List):return ['array',*[expr(x)for x in node.elts]]
        if isinstance(node,ast.Dict):
            if any(not isinstance(k,ast.Constant)or not isinstance(k.value,str)for k in node.keys):raise ValueError('literal object keys required')
            return ['object',{k.value:expr(v)for k,v in zip(node.keys,node.values)}]
        if isinstance(node,ast.Subscript):
            op='at'if isinstance(node.slice,ast.Constant)and type(node.slice.value)is int else'get'
            return [op,expr(node.value),expr(node.slice)]
        if isinstance(node,ast.IfExp):return ['if',expr(node.test),expr(node.body),expr(node.orelse)]
        if version==VERSION and isinstance(node,ast.BinOp)and isinstance(node.op,ast.Add):return ['join',['array',expr(node.left),expr(node.right)],['lit','']]
        if version==VERSION and isinstance(node,ast.JoinedStr):return ['join',['array',*[expr(x.value)if isinstance(x,ast.FormattedValue)else expr(x)for x in node.values]],['lit','']]
        if isinstance(node,ast.BoolOp):return ['and'if isinstance(node.op,ast.And)else'or',*[expr(v)for v in node.values]]
        if isinstance(node,ast.UnaryOp)and isinstance(node.op,ast.Not):return ['not',expr(node.operand)]
        if isinstance(node,ast.Compare)and len(node.ops)==1:
            a,b=expr(node.left),expr(node.comparators[0]);op=node.ops[0]
            if isinstance(op,ast.Eq):return ['eq',a,b]
            if isinstance(op,ast.NotEq):return ['not',['eq',a,b]]
            if isinstance(op,ast.Gt):return ['gt',a,b]
            raise ValueError('only equality and greater-than comparisons allowed')
        if isinstance(node,ast.ListComp):
            if len(node.generators)!=1:raise ValueError('one generator per comprehension')
            g=node.generators[0]
            if not isinstance(g.target,ast.Name)or g.is_async:raise ValueError('named synchronous comprehension binder required')
            name=g.target.id;seq=expr(g.iter);had=name in env;prior=env.get(name);env[name]=['var',name]
            try:
                if g.ifs:seq=['filter',seq,name,['and',*[expr(t)for t in g.ifs]]]
                return ['map',seq,name,expr(node.elt)]
            finally:
                if had:env[name]=prior
                else:env.pop(name,None)
        if isinstance(node,ast.Call)and isinstance(node.func,ast.Attribute)and not node.keywords:
            obj=expr(node.func.value);args=[expr(a)for a in node.args]
            if node.func.attr in ('get','split')and len(args)==1:return [node.func.attr,obj,*args]
            if node.func.attr=='join'and len(args)==1:return ['join',args[0],obj]
            raise ValueError('only pure get/split/join methods allowed')
        if not isinstance(node,ast.Call)or not isinstance(node.func,ast.Name):raise ValueError('pure constructor call or prior name required')
        op=node.func.id.rstrip('_')
        if op=='prototype':
            if len(node.args)!=1 or node.keywords:raise ValueError('prototype takes one binding name')
            name=plain(node.args[0])
            if not isinstance(name,str)or name not in (prototypes or {}):raise ValueError('unknown declared prototype')
            return copy.deepcopy(prototypes[name])
        if op=='len':op='count'
        if op=='lit':
            if len(node.args)!=1 or node.keywords:raise ValueError('lit takes one literal value')
            return ['lit',plain(node.args[0])]
        if op=='var':
            if len(node.args)!=1 or node.keywords or not isinstance(plain(node.args[0]),str):raise ValueError('var takes a literal identifier')
            return ['var',plain(node.args[0])]
        if op=='object':
            if node.args or any(k.arg is None for k in node.keywords):raise ValueError('object_ takes named expression fields only')
            return ['object',{k.arg:expr(k.value)for k in node.keywords}]
        if op not in OPS or node.keywords:raise ValueError('unknown pure constructor: '+op)
        args=[]
        for i,a in enumerate(node.args):
            if op in ('map','filter')and i==1 or op=='let'and i==0:
                value=plain(a)
                if not isinstance(value,str):raise ValueError('literal binder name required')
                args.append(value)
            else:args.append(expr(a))
        return [op,*args]
    for statement in ast.parse(source,mode='exec').body:
        if isinstance(statement,ast.Expr)and isinstance(statement.value,ast.Constant)and isinstance(statement.value.value,str):continue
        if not isinstance(statement,ast.Assign)or len(statement.targets)!=1 or not isinstance(statement.targets[0],ast.Name):
            raise ValueError('only single-name data-construction assignments allowed')
        env[statement.targets[0].id]=expr(statement.value)
    if 'program'not in env:raise ValueError('final program assignment required')
    return env['program']
