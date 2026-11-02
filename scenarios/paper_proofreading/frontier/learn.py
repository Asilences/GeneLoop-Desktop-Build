"""Admit real model source through the existing compiler and sandbox certifier.

The evidence is model construction plus actual sandbox probes, not fabricated
historical Bash calls. Certification still says source equivalence, not quality.
"""
from __future__ import annotations
import json
import os
from pathlib import Path
import shutil
import subprocess

from src.adapters.capability_scene import ROOT,reference
from src.adapters.script_motif_compiler import observe,sha


def learn(program,cases,directory,source_evidence,*,large_output=False):
    directory=Path(directory);directory.mkdir(parents=True,exist_ok=False)
    source=program['source'];command="python3 - <<'FRONTIER_MODEL_PROGRAM'\n"+source+'\nFRONTIER_MODEL_PROGRAM'
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
        observed=observe(command,program['description'],str(work),result.stdout,case['id'],'model-construction-sandbox-probe-'+str(index))
        observed['witness'].update(events_sha256=source_evidence['sha256'],
            input_evidence_scope='model_constructed_source_and_actual_sandbox_probe',source_evidence=source_evidence)
        if large_output:observed['output_limit_bytes']=65536
        if program['mode']=='json':observed['value_binding_requested']=True
        rows.append({'task_id':case['id'],'workspace':str(work),'candidates':[observed] if index==0 else [],
                     'explicit_inputs':[{**item,'sha256':item['source']['sha256']} for item in case['inputs']],
                     'evidence_scope':'model_construction_not_historical_web_task'})
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
