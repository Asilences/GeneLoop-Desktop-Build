"""Read trusted native execution evidence, recompute quality from pinned inputs."""
import argparse,json,sys
from pathlib import Path
ROOT=Path(__file__).resolve().parents[3];sys.path.insert(0,str(ROOT))
from src.adapters.capability_contract import capability_digest
from scenarios.paper_proofreading.frontier.oracle import evaluate,sha


def verify(manifest,trace,spec):
    if spec.get('kind')!='frontier_literal_v1':raise ValueError('frontier_checker_scope_invalid')
    workspace=Path(manifest['workspace']).resolve(strict=True);paths=[]
    for path in spec['input_paths']:
        if path!='/work/inputs/'+Path(path).name:raise ValueError('frontier_checker_input_path_invalid')
        actual=workspace/'inputs'/Path(path).name
        if actual.resolve(strict=True)!=actual or not actual.is_file():raise ValueError('frontier_checker_input_redirected')
        if {'path':path,'sha256':sha(actual.read_bytes())} not in manifest['inputs']:raise ValueError('frontier_checker_input_changed')
        paths.append(actual)
    bound=(trace.get('task_id')==manifest['task_id'] and trace.get('owner')==manifest['owner'] and
           trace.get('status')=='succeeded' and trace.get('input_versions')==manifest['inputs'])
    result=evaluate(spec['role'],paths,trace.get('result'))
    result['checks'].insert(0,{'id':'task_and_versions','status':'passed' if bound else 'failed','observation':'Bound actual owner/task/input versions'})
    result['passed']=bound and result['passed']
    result['evidence_binding']={'trace_sha256':capability_digest(trace),'input_versions_sha256':capability_digest(manifest['inputs'])}
    return result


if __name__=='__main__':
    p=argparse.ArgumentParser()
    for name in ('manifest','trace','specification'):p.add_argument('--'+name,type=Path,required=True)
    a=p.parse_args();print(json.dumps(verify(*[json.loads(getattr(a,n).read_text(encoding='utf-8')) for n in ('manifest','trace','specification')]),ensure_ascii=False))
