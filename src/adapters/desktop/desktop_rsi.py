"""Native host adapter. Privacy, mining, certification and execution reuse shared modules."""
from __future__ import annotations
import dataclasses
import hashlib
import json
import os
from src.adapters.filesystem_paths import Path
import re
import sys
import time
from uuid import uuid4

# Only this private background process loads the isolated NLP dependency kit.
# The six scene tools retain their existing Python dependency resolution.
site=Path(__file__).resolve().parents[4]/'privacy'/'site'
from src.adapters.desktop.desktop_privacy_runtime import prepare
prepare(site)

from src.adapters.geneloop_learning_trace import project, private_json as shared_private_json, sharing_object
from src.adapters.geneloop_privacy import check_material
from src.adapters.harness.dsh_trajectory import ToolContract, extract_dsh_trace, mine_dsh_traces, infer_dsh_provenance
from src.motif_core.offline.compilation.trace_compiler import compile_read_motif, certify_read_motif, artifact_signature
from src.motif_core.runtime.read_executor import run_read_motif

# Other native calls remain barriers; never infer read authorization from a model description.
CONTRACTS = {
    'local_list': ToolContract(('path',), True),
    'local_search': ToolContract(('path', 'query'), True),
    'local_document_pin': ToolContract(('path',), True, ('source_id', 'version_sha256')),
    'local_document_read': ToolContract(('source_id', 'page'), True, provenance_params=('source_id',)),
}
VERSION = hashlib.sha256(b''.join((Path(__file__).parents[3]/p).read_bytes() for p in [
    'src/adapters/desktop/desktop_rsi.py', 'src/adapters/desktop/desktop_privacy_runtime.py', 'src/adapters/harness/dsh_trajectory.py',
    'src/motif_core/trajectory/model.py', 'src/motif_core/offline/mining/trace_mining.py',
    'src/motif_core/offline/mining/motif_miner.py',
    'src/motif_core/offline/compilation/trace_compiler.py', 'src/motif_core/runtime/read_executor.py', 'src/adapters/filesystem_paths.py'])).hexdigest()

def digest(v):
    return hashlib.sha256(json.dumps(v, sort_keys=True, ensure_ascii=False, separators=(',', ':')).encode()).hexdigest()


def private_json(path):
    # Preserve the shared byte/size/link checks while handing it a Win32 IO path.
    # pathlib otherwise copies a PurePath's logical spelling and loses __fspath__.
    return shared_private_json(os.fspath(Path(path)))


def read(path):
    return json.loads(private_json(path))

def save(path, value):
    temporary = path.with_name(path.name+'.'+uuid4().hex+'.tmp')
    with temporary.open('x', encoding='utf-8') as stream:
        os.chmod(temporary, 0o600)
        json.dump(value, stream, ensure_ascii=False, allow_nan=False)
        stream.flush(); os.fsync(stream.fileno())
    temporary.replace(path)

def root_path(value):
    path=Path(value).absolute()
    if path.resolve(strict=True)!=path or path.is_symlink(): raise ValueError('owning_store_required')
    return path

def evidence(root, identity):
    if not re.fullmatch('[a-f0-9]{32}', identity): raise ValueError('invalid_attempt')
    task=root/'tasks'/identity
    meta=read(task/'task.json')
    if meta['principal']!=read(root/'owner.json')['principal'] or meta['attempt_id']!=identity: raise ValueError('foreign_task')
    rows=[json.loads(line) for line in private_json(task/'events.jsonl').decode('utf-8').splitlines() if line]
    if len(rows)>20000:raise ValueError('event_limit')
    return task, meta, rows

def learn(root):
    eligible=[]; excluded=0
    for path in sorted((root/'tasks').glob('*/task.json'))[-100:]:
        try:
            task, meta, events=evidence(root,path.parent.name)
            admitted=read(task/'admission.json')
            if meta['status']!='completed' or admitted['code_version']!=VERSION or meta.get('finished_at',0)+30*86400000<time.time()*1000:continue
            if hashlib.sha256(private_json(task/'events.jsonl')).hexdigest()!=admitted['events_sha256']:continue
            if any(row[1]['session_id']==meta['session_id'] for row in eligible):continue
            prompts=[];versions=[]
            for event in events:
                data=event.get('data',{});message=data.get('message',data)
                if event.get('type')=='user/message' and message.get('source',{}).get('kind')=='user':
                    prompts.extend(' '.join(part['text'].split()).casefold() for part in message.get('content',[]) if part.get('type')=='text')
                if event.get('type')=='tool/result':
                    for part in message.get('content',[]):
                        for block in part.get('content',[]) if part.get('type')=='tool-result' else []:
                            if block.get('type')=='text':
                                try:
                                    value=json.loads(block['text'])
                                    if isinstance(value,dict) and re.fullmatch('[a-f0-9]{64}',value.get('version_sha256','')):versions.append(value['version_sha256'])
                                except (ValueError,TypeError):pass
            fingerprint=digest({'scene':meta['scene'],'prompts':prompts,'source_versions':sorted(set(versions))})
            if any(t.task_fingerprint==fingerprint for t,_ in eligible):continue
            trace=extract_dsh_trace(events,CONTRACTS,trace_id=meta['attempt_id'],task_fingerprint=fingerprint,
                                    provenance_by_call_id=infer_dsh_provenance(events,CONTRACTS))
            # Reuse/unknown-only turns are feedback, not new independent read witnesses.
            if not trace.segments:continue
            eligible.append((trace,meta))
        except (ValueError,OSError,KeyError,TypeError):excluded+=1
    eligible.sort(key=lambda row:row[1]['at'])
    accepted=[]; candidates=0
    for scene in sorted({m['scene'] for _,m in eligible}):
        traces=[t for t,m in eligible if m['scene']==scene]
        if len(traces)<3:continue
        training, holdout=traces[:-1],traces[-1]
        for candidate in mine_dsh_traces(training,min_trace_support=2,max_len=4):
            candidates+=1
            try:
                compiled=compile_read_motif(candidate,training,CONTRACTS)
                certified=certify_read_motif(compiled,holdout,CONTRACTS)
                # A sequence with no witnessed transfer adds no useful executable abstraction.
                if not certified['transfer_evidence']:continue
                key=certified['certified_digest']
                name='motif-'+key[:24]
                path=root/'motifs'/(name+'.json')
                item={'format':'geneloop.desktop-read-motif/v1','id':name,'scene':scene,
                      'code_version':VERSION,'certification_scope':'independent_trace_structure',
                      'quality_cost_promoted':False,'artifact':certified}
                if not path.exists():save(path,item)
                accepted.append(name)
            except (ValueError,KeyError,TypeError):continue
    result={'state':'certified_structure' if accepted else 'waiting_for_independent_evidence',
            'eligible_tasks':len(eligible),'candidates':candidates,'certified':len(set(accepted)),
            'excluded':excluded,'quality_cost_promoted':False,'code_version':VERSION}
    save(root/'learning.json',result)
    return result

def process(root,identity):
    task,meta,events=evidence(root,identity)
    if meta['status'] not in ('completed','failed','cancelled','interrupted'):raise ValueError('task_not_terminal')
    if not events:raise ValueError('no_execution_evidence')
    names=list(dict.fromkeys(e['data']['name'] for e in events if e.get('type')=='tool/call'))
    # Full shared privacy kernel runs before either derived learning or collection.
    visible=project(events,meta['scene'],meta['status'],names,semantic=True)
    save(task/'privacy-learning.json',visible)
    save(task/'admission.json',{'code_version':VERSION,'events_sha256':hashlib.sha256(private_json(task/'events.jsonl')).hexdigest()})
    sample=project(events,meta['scene'],meta['status'],names,semantic=False)
    if sample['nodes']:
        # Preserve true failure/cancellation; v1 manual sharing remains unchanged.
        aliases={}
        sample={**sample,'scene':'generic','nodes':[
            {**n,'tool':None if n['tool'] is None else aliases.setdefault(n['tool'],'tool-'+str(len(aliases)))} for n in sample['nodes']]}
        obj={'format':'geneloop.rsi-collected-object/v1','kind':'tool_flow','trace':sample}
        check_material(obj)
        save(task/'collected-object.json',obj)
    try:learning=learn(root)
    except (ValueError,OSError,KeyError,TypeError):
        learning={'state':'processing_failed','quality_cost_promoted':False,'code_version':VERSION}
        save(root/'learning.json',learning)
    return {'privacy':'admitted','has_object':bool(sample['nodes']),'learning':learning}

def execute(root, request):
    name=request['motif_id']
    if not re.fullmatch('motif-[a-f0-9]{24}',name):raise ValueError('invalid_motif')
    value=read(root/'motifs'/(name+'.json'));artifact=value['artifact']
    if value['code_version']!=VERSION or value['scene']!=request['scene'] or artifact_signature(artifact)!=artifact['certified_digest']:
        raise ValueError('motif_binding_changed')
    if (root/'motifs'/(name+'.suspended')).exists():raise ValueError('motif_suspended')
    owner=read(root/'owner.json')
    for identity in [*artifact['source_trace_ids'],artifact['validation_trace_id']]:
        task,meta,_=evidence(root,identity)
        admission=read(task/'admission.json')
        if meta.get('finished_at',0)+30*86400000<time.time()*1000 or meta['principal']!=owner['principal'] or admission['code_version']!=VERSION or hashlib.sha256(private_json(task/'events.jsonl')).hexdigest()!=admission['events_sha256']:
            raise ValueError('motif_source_changed')
    def call(tool,args):
        print(json.dumps({'kind':'tool','name':tool,'arguments':args}),flush=True)
        reply=json.loads(sys.stdin.readline(1024*1024))
        if reply.get('ok') is not True:raise ValueError('native_tool_failed')
        return reply['value']
    try:
        result=run_read_motif(artifact,contracts=CONTRACTS,bindings=request['bindings'],
            input_version=request['invocation_id'],execute_tool=call,verify_current=lambda:root_path(root),
            is_read_only=lambda name:name in CONTRACTS)
        output={'kind':'result','status':result.status,'outputs':result.outputs,'events':result.events}
        feedback=root/'feedback.jsonl'
        with feedback.open('a',encoding='utf-8') as f:f.write(json.dumps({'motif_id':name,'status':result.status,'invocation_id':request['invocation_id']})+'\n')
        return output
    except Exception:
        (root/'motifs'/(name+'.suspended')).touch(mode=0o600)
        raise

def main():
    root=root_path(sys.argv[2]);mode=sys.argv[1]
    try:
        result=process(root,sys.argv[3]) if mode=='process' else execute(root,json.loads(sys.stdin.readline(256*1024)))
        print(json.dumps(result,ensure_ascii=False),flush=True)
    except Exception:
        print(json.dumps({'kind':'rejected','reason':'local_rsi_processing_rejected'}),flush=True)
        raise SystemExit(1)

if __name__=='__main__':main()
