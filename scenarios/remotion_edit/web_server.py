"""Session adapter over existing Remotion tools; the model authors all edits."""
from pathlib import Path
import base64,hashlib,http.client,importlib.util,json,os,socket,sys,tempfile,time
sys.path.insert(0,str(Path(__file__).resolve().parents[2]))
from src.adapters.session_files import SessionFiles
from mcp.server import MCPServer
from mcp.server.mcpserver.exceptions import ToolError
from mcp.types import ToolAnnotations,CallToolResult
MEDIA={'.mp4','.mov','.webm','.mkv','.mp3','.wav','.m4a','.aac','.ogg','.png','.jpg','.jpeg','.webp','.gif','.svg'}

def fixed_directory(path):
    if path.is_symlink() or path.resolve()!=path.absolute() or not path.is_dir():
        raise ValueError('video workspace must be fixed')
    return path

def atomic_bytes(path,data):
    if path.is_symlink():raise ToolError('video file path changed')
    with tempfile.NamedTemporaryFile(dir=path.parent,prefix='.video-',delete=False) as stream:
        stream.write(data);temporary=Path(stream.name)
    temporary.chmod(0o600);os.replace(temporary,path)

def create_server(inputs):
    files=SessionFiles(inputs);work=files.root.parent;project=work/'remotion'
    project.mkdir(mode=0o700,exist_ok=True);fixed_directory(project)
    for name in ['public','src','out','node_modules']:
        p=project/name;p.mkdir(mode=0o700,exist_ok=True);fixed_directory(p)
    os.environ.update(REMOTION_WORK=str(project),REMOTION_RUNTIME='/runtime',REMOTION_IMAGE='broker-owned',REMOTION_TASK_ASSETS='{}',REMOTION_TASK_NONCE='unbound')
    spec=importlib.util.spec_from_file_location('web_remotion_original',Path(__file__).parent/'structured/server.py')
    scene=importlib.util.module_from_spec(spec);spec.loader.exec_module(scene)
    def grant():
        p=work/'video-output-grant.json'
        if p.is_symlink():raise ToolError('video permission record changed')
        value=json.loads(p.read_text());tid=value['task_id']
        if value.get('schema_version')!=1 or not isinstance(tid,str) or len(tid)!=32 or any(c not in '0123456789abcdef' for c in tid):
            raise ToolError('invalid owning video task')
        return value
    def sync():
        value=grant();manifest=work/'approved-inputs.json'
        if manifest.is_symlink():raise ToolError('source approvals changed')
        files.approved=json.loads(manifest.read_text())['files'];assets={}
        for row in files.list_files()['files']:
            name=row['name']
            if Path(name).suffix.lower() not in MEDIA:continue
            raw,digest=files.read(name,row['sha256']);target=project/'public'/name
            if target.is_symlink() or target.exists() and (not target.is_file() or target.stat().st_nlink!=1):
                raise ToolError('invalid media copy')
            if not target.exists() or hashlib.sha256(target.read_bytes()).hexdigest()!=digest:atomic_bytes(target,raw)
            assets[name]=digest
        scene.ASSETS=assets;scene.NONCE=value['task_id'];return value
    def command(text,timeout_seconds=180):
        started=time.monotonic();root=Path(os.environ['HARLESS_PRIVATE_ROOT']);meta=root/'video-broker.json'
        if meta.is_symlink():raise ToolError('video renderer configuration changed')
        info=json.loads(meta.read_text());path=info['socketPath']
        if info.get('schema_version')!=1 or not isinstance(path,str) or not path.startswith('/') or '\x00' in path:
            raise ToolError('video renderer unavailable')
        conn=http.client.HTTPConnection('localhost',timeout=timeout_seconds+15)
        def connect():
            conn.sock=socket.socket(socket.AF_UNIX,socket.SOCK_STREAM);conn.sock.settimeout(timeout_seconds+15);conn.sock.connect(path)
        conn.connect=connect
        try:
            conn.request('POST','/video',json.dumps({'session':work.parent.name,'command':text}),{'Content-Type':'application/json'})
            response=conn.getresponse()
            if response.status!=200:raise ToolError('video renderer rejected this Session')
            out=[];err=[];code=None
            while True:
                line=response.readline()
                if not line:break
                row=json.loads(line)
                if 'stdout' in row:out.append(base64.b64decode(row['stdout']))
                if 'stderr' in row:err.append(base64.b64decode(row['stderr']))
                if 'exit' in row:code=row['exit']
            result={'exit_code':code if code is not None else 1,'stdout':b''.join(out).decode('utf-8',errors='replace')[-14000:],'stderr':b''.join(err).decode('utf-8',errors='replace')[-8000:]}
            return scene.workspace.emit('run_command',{'command':text,'timeout_seconds':timeout_seconds},result,started)
        finally:conn.close()
    scene.workspace.run_command=command
    broker_command=command
    def run_command(command:str,timeout_seconds:int=180)->dict:
        """Run foreground media analysis in this Session's fixed renderer container.

        /work is the current Remotion project; ffmpeg, ffprobe, Node and the
        installed Remotion runtime are available. No network, credentials,
        foreign Sessions or writable user originals. Use this for actual audio
        samples/volume measurements, not native Bash dependency downloads.
        """
        if type(timeout_seconds) is not int or not 1<=timeout_seconds<=240:
            raise ToolError('media command timeout must be 1..240 seconds')
        return broker_command(command,timeout_seconds)
    source=project/'src/index.tsx'
    if not source.exists():
        source.write_text("import React from 'react';import {registerRoot,Composition} from 'remotion';const Main=()=>null;registerRoot(()=> <Composition id=\"Main\" component={Main} width={640} height={360} fps={30} durationInFrames={180}/>);\n")
    atomic_bytes(project/'package.json',b'{"name":"geneloop-video-session","version":"1.0.0","private":true}')
    base_render=scene.render_composition
    def render_composition(source_version:str)->dict:
        """Render current source, fully decode it, and publish this task's MP4 and editable source."""
        value=sync()
        if value.get('allow_output') is not True:raise ToolError('this task has no output permission')
        result=base_render(source_version)
        current=sync()
        if current!=value:raise ToolError('owning video task changed during rendering')
        destination=work/'outputs/video'/value['task_id']
        destination.mkdir(mode=0o700,parents=True,exist_ok=True);fixed_directory(destination)
        rows=[]
        for name,path in [('video.mp4',project/'out/video.mp4'),('source.tsx',source)]:
            raw=path.read_bytes();target=destination/name;atomic_bytes(target,raw)
            rows.append({'name':target.relative_to(work).as_posix(),'sha256':hashlib.sha256(raw).hexdigest(),'bytes':len(raw)})
        receipt={'schema_version':1,'task_id':value['task_id'],'kind':'video-delivery-v1','source_versions':dict(scene.ASSETS),'source_version':source_version,'full_video_decode':result['full_video_decode'],'files':rows}
        atomic_bytes(destination/'delivery.json',json.dumps(receipt,ensure_ascii=False).encode())
        return {**result,'artifacts':rows,'read_paths':{r['name']:'/artifacts/'+r['name'].removeprefix('outputs/') for r in rows},'mechanical_checks':'decoded_actual_video; model_must_review_pixels'}
    def render_source(text:str)->dict:
        """Write model-authored TSX and actually render it, using the same ordinary renderer."""
        sync();return render_composition(scene.write_source(text)['source_version'])
    def wrapped(fn):
        import functools
        @functools.wraps(fn)
        def call(*args,**kwargs):sync();return fn(*args,**kwargs)
        return call
    server=MCPServer('GeneLoop video editing')
    readers=[scene.list_assets,scene.pin_asset,scene.probe_media,scene.probe_asset,scene.read_source,scene.inspect_render]
    for fn in readers+[scene.write_source,render_composition,scene.write_notes,render_source,run_command]:
        server.tool(annotations=ToolAnnotations(readOnlyHint=fn in readers,destructiveHint=False))(wrapped(fn))
    return server
if __name__=='__main__':create_server(Path(sys.argv[1])).run(transport='stdio')
