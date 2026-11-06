"""Local capability provider: immutable inputs, new versioned outputs, real isolation."""
from __future__ import annotations
import hashlib,json,os,subprocess,sys
from pathlib import Path
from uuid import uuid4
from typing import Annotated
from pydantic import BaseModel,ConfigDict,Field
ROOT=Path(__file__).resolve().parents[2];sys.path.insert(0,str(ROOT))
from src.adapters.session_files import SessionFiles
from mcp.server import MCPServer
from mcp.server.mcpserver.exceptions import ToolError
from mcp.types import ToolAnnotations
class Replacement(BaseModel):
    model_config=ConfigDict(extra='forbid')
    old:str=Field(min_length=1)
    new:str
    expected_count:int=Field(default=1,ge=1,le=10000)
def create_server(work):
    work=Path(work).resolve();files=SessionFiles(work/'inputs');server=MCPServer('general_workspace_runtime')
    def output_allowed():
        p=work/'general-task.json'
        if not p.exists():p=work/'job.json'
        return p.exists() and json.loads(p.read_text()).get('allow_output') is True
    def writable():
        if not output_allowed():raise ToolError('this task is read-only')
    def artifact(destination,text,proof):
        writable()
        if not destination or len(destination)>180 or '\\' in destination or any(p in ('','.','..') for p in destination.split('/')) or any(ord(c)<32 for c in destination):raise ToolError('invalid output-relative destination')
        root=work/'outputs'/'edited'/uuid4().hex;p=root/destination
        if not p.resolve().is_relative_to(root):raise ToolError('output outside task')
        data=text.encode('utf-8')
        if len(data)>2*1024*1024:raise ToolError('text output exceeds 2MiB limit')
        p.parent.mkdir(parents=True,exist_ok=True,mode=0o700)
        with p.open('xb') as stream:stream.write(data)
        p.chmod(0o600);receipt={'path':str(p),'name':destination,'sha256':hashlib.sha256(data).hexdigest(),'bytes':len(data),'derivation':proof,'originals_modified':False}
        (root/'derivation.json').write_text(json.dumps(receipt,ensure_ascii=False));return receipt
    def runtime_capabilities()->dict:
        """Check actual tools and sandbox availability; registration is not a readiness claim."""
        import shutil
        native = bool(os.environ.get('GENELOOP_NATIVE_CODE_RUNNER') and os.environ.get('SSS_PPT_NODE_EXECUTABLE'))
        try:
            command = ([os.environ['SSS_PPT_NODE_EXECUTABLE'], os.environ['GENELOOP_NATIVE_CODE_RUNNER'], '--capabilities']
                       if native else ['docker','image','inspect','node@sha256:9f6d5975c7dca860947d3915877f85607946403fc55349f39b4bc3688448bb6e'])
            probe = subprocess.run(command, capture_output=True, timeout=15)
            d = probe.returncode == 0 and (not native or json.loads(probe.stdout).get('available') is True)
        except (OSError,subprocess.SubprocessError,ValueError):d=False
        ocr = bool(shutil.which('tesseract'))
        if native:
            try:
                import pymupdf
                from src.adapters.geneloop_pdf import tessdata_directory
                ocr = bool(tessdata_directory())
            except (ImportError, OSError, ValueError, KeyError):ocr=False
        return {'code':{'available':d,'language':'typescript/javascript','network':False,'isolation':'QuickJS WASM' if native else 'Docker + upstream worker','cpu_ms':10000,'wall_ms':60000,'memory_mib':64 if native else 256},
            'content_editing':{'available':True,'scope':'new output versions; source files remain unchanged'},
            'ocr':{'available':ocr,'provider':'PyMuPDF + pinned tessdata' if native else 'management.open_document(mode=ocr)'},
            'vision':{'available':True,'provider':'Harness native image attachments and management.view_document_page',
                'requirement':'active model catalog must declare image input; actual request admission remains enforced'},
            'inputs':files.list_files()}
    def edit_text(name:str,sha256:str,replacements:Annotated[list[Replacement],Field(min_length=1,max_length=40)],destination:str)->dict:
        """Apply exact, count-checked literal text edits into a NEW output version.
        Never overwrites inputs; return derivation, source hash and artifact hash.
        """
        writable()
        try:data,version=files.read(name,sha256,limit=2*1024*1024);text=data.decode('utf-8')
        except (ValueError,OSError,UnicodeError) as e:raise ToolError(str(e)) from e
        rows=[]
        for r in replacements:
            if text.count(r.old)!=r.expected_count:raise ToolError('literal edit precondition count differs; no output written')
            text=text.replace(r.old,r.new);rows.append(r.model_dump())
        files.read(name,version)
        return artifact(destination,text,{'kind':'literal_text_edit_v1','source':name,'source_sha256':version,'replacements':rows})
    def create_text(destination:str,text:str)->dict:
        """Create a new text/report artifact under this task's private output directory."""
        return artifact(destination,text,{'kind':'model_authored_text_v1'})
    def execute_code(program:str)->dict:
        """Run TypeScript/JavaScript in the configured isolated worker (native QuickJS or Web Docker).
        Use await inputs.list({}), inputs.read_text({name}), inputs.read_base64({name}),
        outputs.write_text({name,text}); console.log is captured. No host files/network.
        Sources are read-only; new artifacts remain separate from file organization.
        """
        if len(program.encode())>256*1024:raise ToolError('code program exceeds 256KiB')
        allowed=output_allowed()
        native = os.environ.get('GENELOOP_NATIVE_CODE_RUNNER')
        argv = ([os.environ['SSS_PPT_NODE_EXECUTABLE'], native] if native else
                ['node','--experimental-strip-types',str(ROOT/'scenarios/general/runtime_code.ts')])
        child_env={'PATH':os.environ.get('PATH','/usr/bin:/bin:/opt/homebrew/bin'),'LANG':'en_US.UTF-8'}
        if native:
            child_env.update(ELECTRON_RUN_AS_NODE='1', HOME=str(work), USERPROFILE=str(work),
                             TEMP=str(work), TMP=str(work), TMPDIR=str(work))
            for name in ('SystemRoot','SYSTEMROOT','WINDIR'):
                if name in os.environ: child_env[name]=os.environ[name]
        try:r=subprocess.run(argv,
            input=json.dumps({'workspace':str(work),'program':program,'allow_output':allowed}),text=True,capture_output=True,timeout=75,
            env=child_env)
        except (OSError,subprocess.SubprocessError) as e:raise ToolError('code runtime unavailable: '+type(e).__name__) from e
        if r.returncode:raise ToolError('isolated code bridge failed: '+r.stderr[-1200:])
        result=json.loads(r.stdout)
        if result['result'].get('error'):result['status']='execution_failed'
        else:result['status']='completed'
        return result
    for fn in (runtime_capabilities,edit_text,create_text,execute_code):
        server.tool(annotations=ToolAnnotations(readOnlyHint=fn==runtime_capabilities,destructiveHint=False,openWorldHint=False))(fn)
    return server
if __name__=='__main__':create_server(sys.argv[1]).run()
