import json
import subprocess
import pytest
from src.motif_core.offline.compilation.decision_program_construction import PREVIOUS_VERSION,construct,bound_expression


def run(program,value):
    r=subprocess.run(['node','--input-type=module','-e',
        "import {runProgram} from './src/adapters/paper_rsi_program.ts';let s='';for await(const x of process.stdin)s+=x;const v=JSON.parse(s);console.log(JSON.stringify(runProgram(v.program,v.input)));"],
        input=json.dumps({'program':program,'input':value}),capture_output=True,text=True)
    assert r.returncode==0,r.stderr
    return json.loads(r.stdout)


def test_comprehension_scope_and_current_data_lower_to_original_kernel():
    source='''"""An inert description."""
inp = var("input")
xs = inp["rows"]
program = {"values": [x["value"] for x in xs if x["selected"] == True],
           "text": "/".join([x["name"] for x in xs]),
           "empty": len(xs) == 0}
'''
    p=construct(source)
    assert run(p,{'rows':[{'value':3,'name':'a','selected':True},{'value':9,'name':'b','selected':False}]})=={
        'values':[3],'text':'a/b','empty':False}


def test_prototype_captures_existing_lexical_dependencies_without_rewriting_them():
    prototype=['let','x',['lit',3],['let','xs',['array',['var','x'],['lit',4]],['lit',None]]]
    value=bound_expression(prototype,'xs')
    assert run(construct('program = prototype("xs")',{'xs':value}),{})==[3,4]
    assert prototype[-1][-1]==['lit',None]
    with pytest.raises(ValueError,match='no outer binding'):bound_expression(prototype,'missing')


def test_string_expression_support_keeps_the_archived_notation_available():
    basic='inp = var("input")\nprogram = {"name": inp["name"]}'
    assert construct(basic)==construct(basic,version=PREVIOUS_VERSION)
    current='inp = var("input")\nprogram = "file=" + inp["name"]'
    assert run(construct(current),{'name':'fresh.txt'})=='file=fresh.txt'
    with pytest.raises(ValueError):construct(current,version=PREVIOUS_VERSION)


@pytest.mark.parametrize('source',[
    'import os\nprogram = 1', 'program = __import__("os")',
    'program = var("input").__class__', 'program = open("private")',
    'x = var("input")\nx["field"] = 1\nprogram = x',
    'program = [x for x in var("input") for y in var("input")]',
])
def test_construction_is_not_python_execution(source):
    with pytest.raises(ValueError):construct(source)
