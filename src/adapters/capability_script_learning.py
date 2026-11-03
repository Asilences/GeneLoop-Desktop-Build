"""Admit real model source through the existing compiler and sandbox certifier.

The evidence is model construction plus actual sandbox probes, not fabricated
historical Bash calls. Certification still says source equivalence, not quality.
"""
from __future__ import annotations
import json
import ast
import os
from pathlib import Path
import shutil
import subprocess

from src.adapters.capability_scene import ROOT,reference
from src.adapters.script_motif_compiler import observe,sha


def function_module(source):
    tree=ast.parse(source);lines=source.splitlines();kept=[];ignored=[]
    functions={n.name for n in tree.body if isinstance(n,ast.FunctionDef)}
    for node in tree.body:
        declaration=isinstance(node,(ast.Import,ast.ImportFrom,ast.FunctionDef,ast.Assign,ast.AnnAssign))
        if isinstance(node,(ast.Assign,ast.AnnAssign)) and any(
                (isinstance(n,ast.Call) and isinstance(n.func,ast.Name) and n.func.id in functions|{'open','input'}) or
                (isinstance(n,ast.Attribute) and n.attr in ('stdin','argv')) for n in ast.walk(node)):
            declaration=False
        docstring=isinstance(node,ast.Expr) and isinstance(node.value,ast.Constant) and isinstance(node.value.value,str)
        if declaration or docstring:
            first=min([node.lineno,*[d.lineno for d in getattr(node,'decorator_list',[])]])
            kept.append('\n'.join(lines[first-1:node.end_lineno]))
        else:ignored.append({'line':node.lineno,'statement':type(node).__name__})
    return '\n\n'.join(kept)+'\n',ignored


def executable_source(program,cases):
    source=program['source']
    if program.get('interface','script_v1')=='script_v1':return source
    if program['interface']!='function_v1':raise ValueError('frontier_program_interface_invalid')
    tree=ast.parse(source);runs=[n for n in tree.body if isinstance(n,ast.FunctionDef) and n.name=='run']
    if len(runs)!=1 or len(runs[0].args.posonlyargs+runs[0].args.args)!=1 or runs[0].args.vararg or runs[0].args.kwarg or runs[0].args.kwonlyargs:
        raise ValueError('frontier_single_argument_run_function_required')
    if any(isinstance(n,ast.Name) and n.id.startswith('frontier_bridge_') for n in ast.walk(tree)):
        raise ValueError('frontier_reserved_bridge_identifier')
    # function_v1 is a library interface: host invokes run(value). Script main
    # control/output statements are not part of this entrypoint. All function
    # bodies/imports/constants retain their original source text and order.
    source,_=function_module(source)
    paths=[i['path'] for i in cases[0]['inputs']]
    if program['mode']=='json':
        if paths!=['/work/inputs/value.json']:raise ValueError('frontier_json_function_input_invalid')
        payload="frontier_bridge_json.load(open('/work/inputs/value.json',encoding='utf-8'))"
    else:
        if len({Path(p).stem for p in paths})!=len(paths):raise ValueError('frontier_path_function_roles_ambiguous')
        payload=repr({Path(p).stem:p for p in paths})
    return source+"\nimport json as frontier_bridge_json\nfrontier_bridge_input="+payload+"\nprint(frontier_bridge_json.dumps(run(frontier_bridge_input),ensure_ascii=False,separators=(',',':')))\n"


def learn(program,cases,directory,source_evidence,*,large_output=False,origin='model_construction'):
    if origin not in ('model_construction','host_diagnostic'):raise ValueError('frontier_source_origin_invalid')
    directory=Path(directory);directory.mkdir(parents=True,exist_ok=False)
    source=executable_source(program,cases);(directory/'executed-source.py').write_text(source,encoding='utf-8')
    if program.get('interface')=='function_v1':
        (directory/'entrypoint.json').write_text(json.dumps({'interface':'function_v1',
            'ignored_script_main_statements':function_module(program['source'])[1],
            'raw_source_sha256':sha(program['source']),'executed_source_sha256':sha(source)},indent=2),encoding='utf-8')
    command="python3 - <<'FRONTIER_MODEL_PROGRAM'\n"+source+'\nFRONTIER_MODEL_PROGRAM'
    if '\nFRONTIER_MODEL_PROGRAM' in source:raise ValueError('frontier_reserved_boundary')
    rows=[]
    for index,case in enumerate(cases):
        work=directory/('source' if index==0 else 'heldout')
        for part in ('inputs','code','outputs/code','command-tmp'):(work/part).mkdir(parents=True,exist_ok=True)
        for item in case['inputs']:
            raw=Path(item['source']['path']).read_bytes()
            if sha(raw)!=item['source']['sha256']:raise ValueError('frontier_native_input_changed')
            path=item['path']
            if path!='/work/inputs/'+Path(path).name:raise ValueError('frontier_native_path_invalid')
            (work/'inputs'/Path(path).name).write_bytes(raw)
        snippet="import {sandboxRun} from './scripts/certify-script-motifs.mjs';process.stdout.write(sandboxRun(process.argv[1],process.argv[2]));"
        result=subprocess.run(['node','--input-type=module','-e',snippet,str(work),command],cwd=ROOT,capture_output=True,text=True,encoding='utf-8',timeout=45)
        (work/'source-stdout.txt').write_text(result.stdout,encoding='utf-8');(work/'source-stderr.txt').write_text(result.stderr,encoding='utf-8')
        if result.returncode:raise ValueError('frontier_native_source_execution_failed')
        try:observed=observe(command,program['description'],str(work),result.stdout,case['id'],origin+'-sandbox-probe-'+str(index))
        except ValueError as error:
            if getattr(error,'script_diagnostics',None):
                (work/'admission-error.json').write_text(json.dumps(error.script_diagnostics,ensure_ascii=False,indent=2),encoding='utf-8')
            raise
        observed['witness'].update(events_sha256=source_evidence['sha256'],
            input_evidence_scope=origin+'_source_and_actual_sandbox_probe',source_evidence=source_evidence,
            program_interface=program.get('interface','script_v1'),model_source_sha256=sha(program['source']),executed_source_sha256=sha(source))
        if large_output:observed['output_limit_bytes']=65536
        if program['mode']=='json':observed['value_binding_requested']=True
        rows.append({'task_id':case['id'],'workspace':str(work),'candidates':[observed] if index==0 else [],
                     'explicit_inputs':[{**item,'sha256':item['source']['sha256']} for item in case['inputs']],
                     'evidence_scope':origin+'_not_historical_web_task'})
    # Existing certifier fixes its first row as heldout before source selection.
    rows=[rows[1],rows[0]]
    observations=directory/'observations.json';observations.write_text(json.dumps(rows,ensure_ascii=False,indent=2),encoding='utf-8')
    result=subprocess.run(['node','scripts/certify-script-motifs.mjs',str(observations),str(directory)],cwd=ROOT,
                          capture_output=True,text=True,encoding='utf-8',timeout=180)
    (directory/'certifier-stdout.log').write_text(result.stdout,encoding='utf-8');(directory/'certifier-stderr.log').write_text(result.stderr,encoding='utf-8')
    if result.returncode:raise ValueError('frontier_native_certification_process_failed')
    library=json.loads((directory/'library.json').read_text(encoding='utf-8'))
    if not library['programs']:raise ValueError('frontier_native_no_certified_program')
    return reference(directory/'library.json')
